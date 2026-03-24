# sync/tasks.py
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import JiraUser, SyncedIssue, SyncConfig, Tag
from .jira_client import JiraClient
from .gcal_client import GoogleCalendarClient
from .sync_engine import SyncEngine
from .change_detector import ChangeDetector
from .conflict_handler import ConflictHandler

logger = logging.getLogger(__name__)

def get_jira_client() -> JiraClient:
    """Create Jira client from settings."""
    return JiraClient(
        base_url=settings.JIRA_BASE_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN
    )

def get_gcal_client(credentials: Dict[str, Any]) -> GoogleCalendarClient:
    """Create Google Calendar client from credentials."""
    return GoogleCalendarClient(credentials)

def get_sync_engine() -> SyncEngine:
    """Create sync engine with configured clients."""
    return SyncEngine(
        jira_client=get_jira_client(),
        gcal_client_factory=get_gcal_client
    )

@shared_task(bind=True, max_retries=3)
def run_sync(self) -> str:
    """Main sync task that runs every 30 seconds."""
    try:
        configs = list(SyncConfig.objects.filter(is_active=True))

        if not configs:
            return "No active sync configs"

        engine = get_sync_engine()
        jira_client = get_jira_client()
        change_detector = ChangeDetector()

        sync_stats = {
            'jira_to_gcal': 0,
            'gcal_to_jira': 0,
            'conflicts': 0,
            'errors': 0
        }

        # Process each config
        for config in configs:
            try:
                # Get updated Jira issues
                issues = jira_client.get_issues_updated_since(
                    projects=[config.jira_project_key],
                    issue_types=config.issue_types,
                    since_minutes=1,
                    additional_jql=config.additional_jql or ''
                )

                for issue in issues:
                    try:
                        process_jira_issue(engine, issue, sync_stats)
                    except Exception as e:
                        logger.error(f"Error processing Jira issue {issue.get('key')}: {e}")
                        sync_stats['errors'] += 1

            except Exception as e:
                logger.error(f"Error processing config {config.jira_project_key}: {e}")
                sync_stats['errors'] += 1

        # Process Google Calendar changes for all active users
        users = JiraUser.objects.filter(is_active=True).exclude(google_credentials_encrypted='')

        for user in users:
            try:
                process_gcal_changes(engine, user, change_detector, sync_stats)
            except Exception as e:
                logger.error(f"Error processing Google Calendar for {user.email}: {e}")
                sync_stats['errors'] += 1

        # Check for deleted Jira issues and remove calendar events
        check_deleted_issues(engine, jira_client, sync_stats)

        return f"Sync complete: {sync_stats}"

    except Exception as e:
        logger.exception(f"Sync task failed: {e}")
        raise self.retry(exc=e, countdown=10)

def process_jira_issue(
    engine: SyncEngine,
    issue: Dict[str, Any],
    stats: Dict[str, int]
) -> None:
    """Process a single Jira issue for sync."""
    fields = engine.extract_jira_fields(issue)

    if not fields['assignee_id']:
        return  # No assignee, skip

    # Find user - try email first, then Jira account ID
    user = None
    if fields['assignee_email']:
        user = JiraUser.objects.filter(email=fields['assignee_email'], is_active=True).first()
        # Auto-populate Jira account ID if found by email
        if user and fields['assignee_id'] and user.jira_account_id.startswith('pending_'):
            user.jira_account_id = fields['assignee_id']
            user.save()
            logger.info(f"Auto-populated Jira account ID for {user.email}")

    if not user and fields['assignee_id']:
        user = JiraUser.objects.filter(jira_account_id=fields['assignee_id'], is_active=True).first()

    if not user:
        return  # User not set up for sync

    if not user.google_credentials_encrypted:
        return  # No Google credentials

    # Check for existing sync (regardless of sync_enabled status to prevent duplicates)
    synced_issue = SyncedIssue.objects.filter(
        jira_issue_key=fields['key'],
        user=user
    ).first()

    # If task is Done, delete the calendar event (deadline no longer relevant)
    if fields['status'].lower() == 'done':
        if synced_issue and synced_issue.sync_enabled:
            engine.handle_deletion(synced_issue, source='jira')
            logger.info(f"Deleted calendar event for completed task {fields['key']}")
        return

    # If synced_issue exists but was disabled (e.g., task was Done and reopened),
    # we need to re-enable it and create a new calendar event
    if synced_issue and not synced_issue.sync_enabled:
        # Delete the old disabled record and create fresh
        synced_issue.delete()
        synced_issue = None

    engine.sync_jira_to_gcal(user, issue, synced_issue)
    stats['jira_to_gcal'] += 1

def process_gcal_changes(
    engine: SyncEngine,
    user: JiraUser,
    change_detector: ChangeDetector,
    stats: Dict[str, int]
) -> None:
    """Process Google Calendar changes for a user."""
    credentials = json.loads(user.get_google_credentials())
    gcal_client = GoogleCalendarClient(credentials)

    # Get recently updated events
    since = timezone.now() - timedelta(minutes=1)
    events = gcal_client.get_events_updated_since(
        calendar_id=user.google_calendar_id or 'primary',
        since=since
    )

    for event in events:
        try:
            fields = engine.extract_gcal_fields(event)
            issue_key = fields.get('issue_key')

            if not issue_key:
                continue  # Not a synced event

            synced_issue = SyncedIssue.objects.filter(
                jira_issue_key=issue_key,
                user=user,
                sync_enabled=True
            ).first()

            if not synced_issue:
                continue

            # Detect changes
            gcal_changes = change_detector.detect_changes(
                synced_issue.field_checksums,
                fields
            )

            if not gcal_changes:
                continue

            # Check for Jira changes too (conflict detection)
            jira_issue = engine.jira_client.get_issue(issue_key)
            jira_fields = engine.extract_jira_fields(jira_issue)
            jira_changes = change_detector.detect_changes(
                synced_issue.field_checksums,
                jira_fields
            )

            # Find conflicts
            conflicts = change_detector.find_conflicts(jira_changes, gcal_changes)

            if conflicts:
                # Create conflict in Jira
                for field_name, conflict_data in conflicts.items():
                    engine.conflict_handler.create_conflict_in_jira(
                        issue_key=issue_key,
                        field_name=field_name,
                        jira_value=conflict_data['jira_value'],
                        gcal_value=conflict_data['gcal_value']
                    )
                stats['conflicts'] += len(conflicts)
            else:
                # No conflict, sync from Google Calendar to Jira
                engine.sync_gcal_to_jira(synced_issue, event)
                stats['gcal_to_jira'] += 1

        except Exception as e:
            logger.error(f"Error processing calendar event {event.get('id')}: {e}")
            stats['errors'] += 1


def check_deleted_issues(
    engine: SyncEngine,
    jira_client: JiraClient,
    stats: Dict[str, int]
) -> None:
    """Check for deleted Jira issues and remove their calendar events."""
    import requests

    # Get all synced issues that are still enabled
    synced_issues = SyncedIssue.objects.filter(sync_enabled=True)

    for synced_issue in synced_issues:
        try:
            # Try to fetch the issue from Jira
            jira_client.get_issue(synced_issue.jira_issue_key)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Issue was deleted in Jira - delete calendar event
                try:
                    engine.handle_deletion(synced_issue, source='jira')
                    logger.info(f"Deleted calendar event for removed Jira issue {synced_issue.jira_issue_key}")
                except Exception as del_error:
                    logger.error(f"Error deleting calendar event for {synced_issue.jira_issue_key}: {del_error}")
                    stats['errors'] += 1
        except Exception as e:
            # Other errors - log but don't treat as deletion
            logger.debug(f"Error checking issue {synced_issue.jira_issue_key}: {e}")
