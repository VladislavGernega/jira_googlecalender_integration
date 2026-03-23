# tests/test_jira_client.py
import pytest
from unittest.mock import Mock, patch
from sync.jira_client import JiraClient

class TestJiraClient:
    @pytest.fixture
    def client(self):
        return JiraClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token"
        )

    def test_build_auth_header(self, client):
        headers = client._build_headers()

        assert 'Authorization' in headers
        assert headers['Authorization'].startswith('Basic ')
        assert headers['Content-Type'] == 'application/json'

    @patch('sync.jira_client.requests.get')
    def test_get_issues_updated_since(self, mock_get, client):
        mock_response = Mock()
        mock_response.json.return_value = {
            'issues': [
                {
                    'key': 'TEST-1',
                    'id': '10001',
                    'fields': {
                        'summary': 'Test issue',
                        'duedate': '2024-03-25',
                        'assignee': {'accountId': 'user123', 'displayName': 'John'},
                        'status': {'name': 'In Progress'},
                        'priority': {'name': 'High'},
                        'labels': ['PM'],
                        'description': 'Test description',
                        'updated': '2024-03-20T10:00:00.000+0000'
                    }
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        issues = client.get_issues_updated_since(
            projects=['TEST'],
            issue_types=['Task'],
            since_minutes=5
        )

        assert len(issues) == 1
        assert issues[0]['key'] == 'TEST-1'

    @patch('sync.jira_client.requests.put')
    def test_update_issue(self, mock_put, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        client.update_issue('TEST-1', {'summary': 'Updated title'})

        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert 'TEST-1' in call_args[0][0]

    @patch('sync.jira_client.requests.post')
    def test_add_comment(self, mock_post, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client.add_comment('TEST-1', 'Sync conflict detected')

        mock_post.assert_called_once()

    @patch('sync.jira_client.requests.put')
    def test_add_label(self, mock_put, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        client.add_label('TEST-1', 'sync-conflict')

        mock_put.assert_called_once()
