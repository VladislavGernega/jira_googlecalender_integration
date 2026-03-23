# tests/test_gcal_client.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from sync.gcal_client import GoogleCalendarClient

class TestGoogleCalendarClient:
    @pytest.fixture
    def mock_credentials(self):
        return {
            'token': 'access-token',
            'refresh_token': 'refresh-token',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'client-id',
            'client_secret': 'client-secret'
        }

    @pytest.fixture
    def client(self, mock_credentials):
        with patch('sync.gcal_client.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            return GoogleCalendarClient(mock_credentials)

    def test_create_event(self, client):
        client.service.events().insert().execute.return_value = {
            'id': 'event123',
            'summary': '[PM] Test Task - TEST-1'
        }

        event_id = client.create_event(
            calendar_id='primary',
            summary='Test Task',
            due_date=datetime(2024, 3, 25),
            description='Test description',
            tag='PM',
            issue_key='TEST-1',
            issue_url='https://test.atlassian.net/browse/TEST-1',
            color_id=10
        )

        assert event_id == 'event123'

    def test_update_event(self, client):
        client.service.events().update().execute.return_value = {'id': 'event123'}

        client.update_event(
            calendar_id='primary',
            event_id='event123',
            summary='Updated Task',
            due_date=datetime(2024, 3, 26)
        )

        client.service.events().update.assert_called()

    def test_delete_event(self, client):
        client.service.events().delete().execute.return_value = None

        client.delete_event(calendar_id='primary', event_id='event123')

        client.service.events().delete.assert_called()

    def test_get_events_updated_since(self, client):
        client.service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': '[PM] Task 1 - TEST-1',
                    'updated': '2024-03-20T10:00:00Z'
                }
            ]
        }

        events = client.get_events_updated_since(
            calendar_id='primary',
            since=datetime(2024, 3, 20)
        )

        assert len(events) == 1
        assert events[0]['id'] == 'event1'
