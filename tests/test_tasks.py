# tests/test_tasks.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from sync.tasks import run_sync, get_jira_client, get_sync_engine

class TestTasks:
    @patch('sync.tasks.JiraClient')
    def test_get_jira_client(self, mock_jira_client):
        with patch('sync.tasks.settings') as mock_settings:
            mock_settings.JIRA_BASE_URL = 'https://test.atlassian.net'
            mock_settings.JIRA_EMAIL = 'test@test.com'
            mock_settings.JIRA_API_TOKEN = 'token123'

            client = get_jira_client()

        mock_jira_client.assert_called_once()

    @patch('sync.tasks.get_jira_client')
    @patch('sync.tasks.SyncConfig.objects')
    @patch('sync.tasks.JiraUser.objects')
    def test_run_sync_no_configs(self, mock_users, mock_configs, mock_get_client):
        mock_configs.filter.return_value = []

        result = run_sync()

        assert 'No active sync configs' in result
