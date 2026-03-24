# sync/sync_engine.py
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Tuple
from django.utils import timezone

from .models import JiraUser, SyncedIssue, SyncConfig, SyncHistory, Tag, Conflict
from .jira_client import JiraClient
from .gcal_client import GoogleCalendarClient
from .tag_parser import TagParser
from .change_detector import ChangeDetector
from .conflict_handler import ConflictHandler

class SyncEngine:
    """Orchestrates bidirectional sync between Jira and Google Calendar."""

    # Regex patterns for parsing time from summary
    TIME_PATTERNS = [
        # "2:30pm", "2:30 pm", "2:30PM", "2:30 PM"
        r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)',
        # "2pm", "2 pm", "2PM", "2 PM"
        r'(\d{1,2})\s*(am|pm|AM|PM)',
        # "14:00", "14:30" (24-hour format)
        r'(\d{1,2}):(\d{2})(?!\s*[ap])',
    ]

    def __init__(
        self,
        jira_client: JiraClient,
        gcal_client_factory: Callable[[Dict], GoogleCalendarClient]
    ):
        self.jira_client = jira_client
        self.gcal_client_factory = gcal_client_factory
        self.tag_parser = TagParser()
        self.change_detector = ChangeDetector()
        self.conflict_handler = ConflictHandler(jira_client)

    def parse_time_from_summary(self, summary: str) -> Tuple[int, int]:
        """
        Parse time from issue summary.
        Returns (hour, minute) tuple. Defaults to (8, 0) if no time found.

        Supports formats:
        - "2pm", "2:30pm", "2 pm", "2:30 pm"
        - "14:00", "14:30" (24-hour)
        - "2:00 PM", "11:30 AM"
        - "at 5", "by 3" (bare numbers, assumes PM for 1-7)
        """
        # Pattern 1: "2:30pm" or "2:30 pm"
        match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', summary, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            period = match.group(3).lower()
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            return (hour, minute)

        # Pattern 2: "2pm" or "2 pm" (no minutes)
        match = re.search(r'(\d{1,2})\s*(am|pm)', summary, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            period = match.group(2).lower()
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            return (hour, 0)

        # Pattern 3: "14:00" (24-hour format, but not followed by am/pm)
        match = re.search(r'(\d{1,2}):(\d{2})(?!\s*[ap]m)', summary, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                # If hour is 1-7 and no am/pm specified, assume PM (business hours)
                if 1 <= hour <= 7:
                    hour += 12
                return (hour, minute)

        # Pattern 4: Bare number at end like "by 5", "at 3", or just "task 5"
        # Look for standalone number (1-12) near end of summary
        match = re.search(r'(?:at|by|@)?\s*(\d{1,2})(?:\s*$|\s+(?:today|tomorrow|eod|end))', summary, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            if 1 <= hour <= 12:
                # Assume PM for 1-7, AM for 8-12 (business hours heuristic)
                if 1 <= hour <= 7:
                    hour += 12
                return (hour, 0)

        # Default to 8:00 AM if no time found
        return (8, 0)

    def extract_jira_fields(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from Jira issue."""
        fields = issue.get('fields', {})

        # Extract description text
        description = ''
        desc_field = fields.get('description')
        if desc_field and isinstance(desc_field, dict):
            # Atlassian Document Format
            try:
                content = desc_field.get('content', [])
                texts = []
                for block in content:
                    for item in block.get('content', []):
                        if item.get('type') == 'text':
                            texts.append(item.get('text', ''))
                description = '\n'.join(texts)
            except (KeyError, TypeError):
                description = str(desc_field)
        elif desc_field:
            description = str(desc_field)

        # Extract assignee info
        assignee = fields.get('assignee') or {}

        # Extract other assignees from custom field
        # Look for common custom field patterns for "Other Assignees"
        other_assignees = []
        for field_key, field_value in fields.items():
            if field_key.startswith('customfield_') and isinstance(field_value, list):
                # Check if it's a list of users (has accountId)
                if field_value and isinstance(field_value[0], dict) and 'accountId' in field_value[0]:
                    other_assignees = [
                        {
                            'id': u.get('accountId'),
                            'name': u.get('displayName', ''),
                            'email': u.get('emailAddress', '')
                        }
                        for u in field_value
                    ]
                    break  # Found the user picker field

        # Get issue type for color coding
        issue_type = fields.get('issuetype', {}).get('name', '')

        # Get labels (kept for reference but not used for colors)
        labels = fields.get('labels', [])

        return {
            'key': issue.get('key'),
            'id': issue.get('id'),
            'summary': fields.get('summary', ''),
            'due_date': fields.get('duedate'),
            'description': description,
            'status': fields.get('status', {}).get('name', ''),
            'priority': fields.get('priority', {}).get('name', ''),
            'issue_type': issue_type,
            'tag': issue_type,  # Use issue type as tag for calendar title/color
            'labels': labels,
            'assignee_id': assignee.get('accountId'),
            'assignee_name': assignee.get('displayName', ''),
            'assignee_email': assignee.get('emailAddress', ''),
            'other_assignees': other_assignees,
            'updated': fields.get('updated'),
            'project_key': issue.get('key', '').split('-')[0]
        }

    def extract_gcal_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from Google Calendar event."""
        summary = event.get('summary', '')
        tag, clean_title = self.tag_parser.parse_title(summary)
        issue_key = self.tag_parser.extract_issue_key(summary)

        # Remove issue key from title to get just the summary
        if issue_key:
            clean_title = clean_title.replace(f' - {issue_key}', '').strip()

        # Parse due date from start time
        start = event.get('start', {})
        start_dt = start.get('dateTime') or start.get('date')
        due_date = None
        if start_dt:
            try:
                if 'T' in start_dt:
                    due_date = start_dt.split('T')[0]
                else:
                    due_date = start_dt
            except (ValueError, IndexError):
                pass

        # Extract description and metadata
        full_desc = event.get('description', '')
        # Find content between the separator lines
        parts = full_desc.split('─' * 40)
        description = parts[1].strip() if len(parts) > 2 else ''

        # Parse priority from metadata section (first part before separator)
        priority = None
        if parts:
            metadata = parts[0]
            priority_match = re.search(r'Priority:\s*(\w+)', metadata)
            if priority_match:
                priority = priority_match.group(1)

        return {
            'event_id': event.get('id'),
            'summary': clean_title,
            'tag': tag,
            'issue_key': issue_key,
            'due_date': due_date,
            'description': description,
            'priority': priority,
            'updated': event.get('updated')
        }

    def should_sync_issue(self, issue: Dict[str, Any]) -> bool:
        """Check if issue matches any active sync config."""
        project_key = issue.get('key', '').split('-')[0]
        issue_type = issue.get('fields', {}).get('issuetype', {}).get('name')

        configs = SyncConfig.objects.filter(
            jira_project_key=project_key,
            is_active=True
        )

        for config in configs:
            if issue_type in config.issue_types:
                return True

        return False

    def get_or_create_tag(self, tag_name: str) -> Tag:
        """Get existing tag or create new one with auto-assigned color."""
        # Case-insensitive lookup first
        tag = Tag.objects.filter(name__iexact=tag_name).first()
        if tag:
            return tag

        # Create new tag if not found
        tag, created = Tag.objects.get_or_create(
            name=tag_name,
            defaults={
                'color_hex': '#808080',
                'google_color_id': 8
            }
        )
        return tag

    def sync_jira_to_gcal(
        self,
        user: JiraUser,
        jira_issue: Dict[str, Any],
        synced_issue: Optional[SyncedIssue] = None
    ) -> SyncedIssue:
        """Sync a Jira issue to Google Calendar."""
        fields = self.extract_jira_fields(jira_issue)
        credentials = json.loads(user.get_google_credentials())
        gcal_client = self.gcal_client_factory(credentials)

        # Get tag color
        color_id = 8
        if fields['tag']:
            tag = self.get_or_create_tag(fields['tag'])
            color_id = tag.google_color_id

        # Override color based on priority (Medium keeps tag's default color)
        if fields['priority'] in ('High', 'Highest'):
            color_id = 11  # Red
        elif fields['priority'] in ('Low', 'Lowest'):
            color_id = 9   # Blue

        jira_base_url = self.jira_client.base_url
        issue_url = f"{jira_base_url}/browse/{fields['key']}"

        # Parse time from summary, default to 8:00 AM
        hour, minute = self.parse_time_from_summary(fields['summary'])
        due_date = datetime.strptime(fields['due_date'], '%Y-%m-%d')
        due_date = due_date.replace(hour=hour, minute=minute)

        if synced_issue:
            # Update existing event
            title = self.tag_parser.format_title(
                fields['tag'], fields['summary'], fields['key']
            )
            gcal_client.update_event(
                calendar_id=user.google_calendar_id or 'primary',
                event_id=synced_issue.google_event_id,
                summary=title,
                due_date=due_date,
                color_id=color_id
            )
            action = 'updated'
        else:
            # Double-check no existing sync record (race condition prevention)
            existing = SyncedIssue.objects.filter(
                jira_issue_key=fields['key'],
                user=user,
                sync_enabled=True
            ).first()

            if existing:
                # Another sync cycle already created it, just update
                synced_issue = existing
                title = self.tag_parser.format_title(
                    fields['tag'], fields['summary'], fields['key']
                )
                gcal_client.update_event(
                    calendar_id=user.google_calendar_id or 'primary',
                    event_id=synced_issue.google_event_id,
                    summary=title,
                    due_date=due_date,
                    color_id=color_id
                )
                action = 'updated'
            else:
                # Create new event
                event_id = gcal_client.create_event(
                    calendar_id=user.google_calendar_id or 'primary',
                    summary=fields['summary'],
                    due_date=due_date,
                    description=fields['description'],
                    tag=fields['tag'],
                    issue_key=fields['key'],
                    issue_url=issue_url,
                    color_id=color_id,
                    status=fields['status'],
                    priority=fields['priority'],
                    assignee=fields['assignee_name']
                )

                # Use get_or_create to prevent race condition duplicates
                synced_issue, created = SyncedIssue.objects.get_or_create(
                    jira_issue_key=fields['key'],
                    user=user,
                    defaults={
                        'jira_issue_id': fields['id'],
                        'google_event_id': event_id,
                        'sync_enabled': True
                    }
                )

                if not created:
                    # Record already existed (race condition), update the event_id
                    synced_issue.google_event_id = event_id
                    synced_issue.sync_enabled = True

                action = 'created'

        # Update checksums
        synced_issue.field_checksums = self.change_detector.build_checksums(fields)
        synced_issue.last_jira_update = timezone.now()
        synced_issue.save()

        # Log history
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action=action,
            source='jira',
            field_changes=fields
        )

        return synced_issue

    def sync_gcal_to_jira(
        self,
        synced_issue: SyncedIssue,
        gcal_event: Dict[str, Any]
    ) -> None:
        """Sync Google Calendar changes back to Jira."""
        fields = self.extract_gcal_fields(gcal_event)

        # Build update payload
        jira_updates = {}

        if fields['summary']:
            jira_updates['summary'] = fields['summary']

        if fields['due_date']:
            jira_updates['duedate'] = fields['due_date']

        # Note: Issue type (tag) is NOT synced from Google Calendar to Jira
        # Issue types are set in Jira and control calendar colors

        # Note: Priority is NOT synced from Google Calendar to Jira
        # Jira is the source of truth for priority

        if jira_updates:
            self.jira_client.update_issue(synced_issue.jira_issue_key, jira_updates)

        # Update checksums
        synced_issue.field_checksums = self.change_detector.build_checksums(fields)
        synced_issue.last_gcal_update = timezone.now()
        synced_issue.save()

        # Log history
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action='updated',
            source='gcal',
            field_changes=fields
        )

    def handle_deletion(
        self,
        synced_issue: SyncedIssue,
        source: str
    ) -> None:
        """Handle deletion from either system."""
        user = synced_issue.user

        if source == 'jira':
            # Jira issue deleted -> delete calendar event
            credentials = json.loads(user.get_google_credentials())
            gcal_client = self.gcal_client_factory(credentials)
            try:
                gcal_client.delete_event(
                    calendar_id=user.google_calendar_id or 'primary',
                    event_id=synced_issue.google_event_id
                )
            except Exception:
                pass  # Event may already be deleted

        elif source == 'gcal':
            # Calendar event deleted -> delete Jira issue
            try:
                self.jira_client.delete_issue(synced_issue.jira_issue_key)
            except Exception:
                pass  # Issue may already be deleted

        # Log and archive
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action='deleted',
            source=source,
            field_changes={'deleted_from': source}
        )

        synced_issue.sync_enabled = False
        synced_issue.save()
