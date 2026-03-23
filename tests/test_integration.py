# tests/test_integration.py
import pytest
from django.test import TestCase

class TestImports(TestCase):
    def test_all_modules_import(self):
        from sync.models import JiraUser, SyncedIssue, Tag, SyncConfig, SyncHistory, Conflict
        from sync.encryption import TokenEncryptor
        from sync.jira_client import JiraClient
        from sync.gcal_client import GoogleCalendarClient
        from sync.tag_parser import TagParser
        from sync.change_detector import ChangeDetector
        from sync.conflict_handler import ConflictHandler
        from sync.sync_engine import SyncEngine
        from sync.tasks import run_sync

        assert True  # All imports succeeded

    def test_model_structure(self):
        from sync.models import JiraUser, Tag, SyncConfig, SyncedIssue, SyncHistory, Conflict

        # Verify all models have required fields
        assert hasattr(JiraUser, 'jira_account_id')
        assert hasattr(JiraUser, 'email')
        assert hasattr(JiraUser, 'google_credentials_encrypted')

        assert hasattr(Tag, 'name')
        assert hasattr(Tag, 'color_hex')
        assert hasattr(Tag, 'google_color_id')

        assert hasattr(SyncConfig, 'jira_project_key')
        assert hasattr(SyncConfig, 'issue_types')

        assert hasattr(SyncedIssue, 'jira_issue_key')
        assert hasattr(SyncedIssue, 'google_event_id')
        assert hasattr(SyncedIssue, 'field_checksums')

        assert hasattr(SyncHistory, 'action')
        assert hasattr(SyncHistory, 'source')

        assert hasattr(Conflict, 'field_name')
        assert hasattr(Conflict, 'status')
