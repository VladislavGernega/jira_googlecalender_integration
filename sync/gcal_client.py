# sync/gcal_client.py
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GoogleCalendarClient:
    """Wrapper for Google Calendar API."""

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, credentials_dict: Dict[str, Any]):
        """Initialize with credentials dictionary."""
        self.credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=self.SCOPES
        )
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        due_date: datetime,
        description: str,
        tag: Optional[str],
        issue_key: str,
        issue_url: str,
        color_id: int = 8,
        status: str = '',
        priority: str = '',
        assignee: str = ''
    ) -> str:
        """Create a calendar event and return event ID."""
        # Format title with tag
        title = f"[{tag}] {summary} - {issue_key}" if tag else f"{summary} - {issue_key}"

        # Build description with metadata
        desc_parts = []
        if status:
            desc_parts.append(f"Status: {status}")
        if priority:
            desc_parts.append(f"Priority: {priority}")
        if assignee:
            desc_parts.append(f"Assignee: {assignee}")
        if desc_parts:
            desc_parts.append("─" * 40)
        if description:
            desc_parts.append(description)
        desc_parts.append("─" * 40)
        desc_parts.append(f"🔗 {issue_url}")

        full_description = "\n".join(desc_parts)

        # Event ENDS at deadline time, 5 min duration (so it's a reminder before deadline)
        end_time = due_date.replace(second=0, microsecond=0)
        start_time = end_time - timedelta(minutes=5)

        event = {
            'summary': title,
            'description': full_description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Chicago',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Chicago',
            },
            'colorId': str(color_id),
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 0},  # At deadline time
                ],
            },
        }

        result = self.service.events().insert(calendarId=calendar_id, body=event).execute()
        return result['id']

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        summary: Optional[str] = None,
        due_date: Optional[datetime] = None,
        description: Optional[str] = None,
        color_id: Optional[int] = None
    ) -> None:
        """Update an existing calendar event."""
        # Get current event
        event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if summary is not None:
            event['summary'] = summary

        if due_date is not None:
            # Event ENDS at deadline time, 5 min duration
            end_time = due_date.replace(second=0, microsecond=0)
            start_time = end_time - timedelta(minutes=5)
            event['start'] = {'dateTime': start_time.isoformat(), 'timeZone': 'America/Chicago'}
            event['end'] = {'dateTime': end_time.isoformat(), 'timeZone': 'America/Chicago'}

        if description is not None:
            event['description'] = description

        if color_id is not None:
            event['colorId'] = str(color_id)

        self.service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete a calendar event."""
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    def get_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
        """Get a single event by ID."""
        return self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    def get_events_updated_since(
        self,
        calendar_id: str,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """Get events updated since given time."""
        # Format datetime properly for Google API (RFC3339)
        # Remove timezone info and add Z for UTC
        if since.tzinfo is not None:
            # Convert to UTC and remove tzinfo
            from datetime import timezone
            since_utc = since.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            since_utc = since
        updated_min = since_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        result = self.service.events().list(
            calendarId=calendar_id,
            updatedMin=updated_min,
            singleEvents=True,
            orderBy='updated'
        ).execute()

        return result.get('items', [])
