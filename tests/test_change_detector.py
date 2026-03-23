import pytest
import hashlib
from sync.change_detector import ChangeDetector

class TestChangeDetector:
    @pytest.fixture
    def detector(self):
        return ChangeDetector()

    def test_compute_checksum(self, detector):
        checksum = detector.compute_checksum("test value")

        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256 hex length

    def test_same_value_same_checksum(self, detector):
        checksum1 = detector.compute_checksum("test value")
        checksum2 = detector.compute_checksum("test value")

        assert checksum1 == checksum2

    def test_detect_no_changes(self, detector):
        old_checksums = {'summary': 'abc123', 'due_date': 'def456'}
        new_data = {'summary': 'abc123', 'due_date': 'def456'}

        changes = detector.detect_changes(old_checksums, new_data)

        assert changes == {}

    def test_detect_single_field_change(self, detector):
        old_checksums = {
            'summary': detector.compute_checksum('Old Title'),
            'due_date': detector.compute_checksum('2024-03-25')
        }
        new_data = {
            'summary': 'New Title',
            'due_date': '2024-03-25'
        }

        changes = detector.detect_changes(old_checksums, new_data)

        assert 'summary' in changes
        assert changes['summary']['old_checksum'] == old_checksums['summary']
        assert 'due_date' not in changes

    def test_detect_conflict(self, detector):
        jira_changes = {'due_date': {'new_value': '2024-03-28'}}
        gcal_changes = {'due_date': {'new_value': '2024-03-26'}}

        conflicts = detector.find_conflicts(jira_changes, gcal_changes)

        assert 'due_date' in conflicts
        assert conflicts['due_date']['jira_value'] == '2024-03-28'
        assert conflicts['due_date']['gcal_value'] == '2024-03-26'

    def test_no_conflict_different_fields(self, detector):
        jira_changes = {'summary': {'new_value': 'New Title'}}
        gcal_changes = {'due_date': {'new_value': '2024-03-26'}}

        conflicts = detector.find_conflicts(jira_changes, gcal_changes)

        assert conflicts == {}

    def test_build_checksums(self, detector):
        data = {
            'summary': 'Test Title',
            'due_date': '2024-03-25',
            'description': 'Test desc'
        }

        checksums = detector.build_checksums(data)

        assert 'summary' in checksums
        assert 'due_date' in checksums
        assert 'description' in checksums
