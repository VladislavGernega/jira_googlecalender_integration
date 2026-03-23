# tests/test_sync_engine.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from sync.sync_engine import SyncEngine

class TestSyncEngine:
    @pytest.fixture
    def mock_jira_client(self):
        return Mock()

    @pytest.fixture
    def mock_gcal_client_factory(self):
        return Mock(return_value=Mock())

    @pytest.fixture
    def engine(self, mock_jira_client, mock_gcal_client_factory):
        return SyncEngine(mock_jira_client, mock_gcal_client_factory)

    def test_extract_jira_fields(self, engine):
        jira_issue = {
            'key': 'TEST-1',
            'id': '10001',
            'fields': {
                'summary': 'Test Task',
                'duedate': '2024-03-25',
                'description': {'content': [{'content': [{'type': 'text', 'text': 'Desc'}]}]},
                'status': {'name': 'In Progress'},
                'priority': {'name': 'High'},
                'labels': ['PM', 'urgent'],
                'assignee': {'accountId': 'user123', 'displayName': 'John', 'emailAddress': 'john@test.com'},
                'updated': '2024-03-20T10:00:00.000+0000'
            }
        }

        fields = engine.extract_jira_fields(jira_issue)

        assert fields['summary'] == 'Test Task'
        assert fields['due_date'] == '2024-03-25'
        assert fields['tag'] == 'PM'
        assert fields['status'] == 'In Progress'
        assert fields['assignee_email'] == 'john@test.com'

    def test_extract_gcal_fields(self, engine):
        gcal_event = {
            'id': 'event123',
            'summary': '[PM] Test Task - TEST-1',
            'start': {'dateTime': '2024-03-25T08:00:00Z'},
            'description': 'Status: In Progress\nPriority: High\n────────────────────────────────────────\nDesc\n────────────────────────────────────────\n🔗 https://test.atlassian.net/browse/TEST-1',
            'updated': '2024-03-20T10:00:00Z'
        }

        fields = engine.extract_gcal_fields(gcal_event)

        assert fields['summary'] == 'Test Task'
        assert fields['tag'] == 'PM'
        assert fields['issue_key'] == 'TEST-1'

    def test_should_sync_issue_with_matching_config(self, engine):
        issue = {'key': 'TEST-1', 'fields': {'issuetype': {'name': 'Task'}}}
        config = Mock(jira_project_key='TEST', issue_types=['Task'], is_active=True)

        with patch('sync.sync_engine.SyncConfig.objects') as mock_qs:
            mock_qs.filter.return_value = [config]

            result = engine.should_sync_issue(issue)

        assert result is True
