import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from sync.conflict_handler import ConflictHandler

class TestConflictHandler:
    @pytest.fixture
    def mock_jira_client(self):
        return Mock()

    @pytest.fixture
    def handler(self, mock_jira_client):
        return ConflictHandler(mock_jira_client)

    def test_format_conflict_comment(self, handler):
        comment = handler.format_conflict_comment(
            field_name='due_date',
            jira_value='March 28, 2024',
            gcal_value='March 26, 2024'
        )

        assert 'Sync Conflict' in comment
        assert 'due_date' in comment or 'Due date' in comment
        assert 'March 28, 2024' in comment
        assert 'March 26, 2024' in comment

    def test_create_conflict_in_jira(self, handler, mock_jira_client):
        handler.create_conflict_in_jira(
            issue_key='TEST-1',
            field_name='due_date',
            jira_value='2024-03-28',
            gcal_value='2024-03-26'
        )

        mock_jira_client.add_comment.assert_called_once()
        mock_jira_client.add_label.assert_called_once_with('TEST-1', 'sync-conflict')

    def test_resolve_conflict_in_jira(self, handler, mock_jira_client):
        handler.resolve_conflict_in_jira(issue_key='TEST-1')

        mock_jira_client.remove_label.assert_called_once_with('TEST-1', 'sync-conflict')
        mock_jira_client.add_comment.assert_called_once()

        comment_text = mock_jira_client.add_comment.call_args[0][1]
        assert 'resolved' in comment_text.lower()

    def test_format_field_name_for_display(self, handler):
        assert handler._format_field_name('due_date') == 'Due date'
        assert handler._format_field_name('summary') == 'Summary'
