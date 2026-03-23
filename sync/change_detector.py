import hashlib
from typing import Dict, Any, Optional

class ChangeDetector:
    """Detects field-level changes between sync cycles."""

    TRACKED_FIELDS = ['summary', 'due_date', 'description', 'tag', 'status', 'priority']

    def compute_checksum(self, value: Any) -> str:
        """Compute SHA256 checksum of a value."""
        str_value = str(value) if value is not None else ''
        return hashlib.sha256(str_value.encode()).hexdigest()

    def build_checksums(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Build checksums for all tracked fields in data."""
        return {
            field: self.compute_checksum(data.get(field))
            for field in self.TRACKED_FIELDS
            if field in data
        }

    def detect_changes(
        self,
        old_checksums: Dict[str, str],
        new_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Detect which fields have changed.

        Returns:
            Dict of field_name -> {old_checksum, new_checksum, new_value}
        """
        changes = {}

        for field, old_checksum in old_checksums.items():
            if field not in new_data:
                continue

            new_value = new_data[field]
            new_checksum = self.compute_checksum(new_value)

            if new_checksum != old_checksum:
                changes[field] = {
                    'old_checksum': old_checksum,
                    'new_checksum': new_checksum,
                    'new_value': new_value
                }

        return changes

    def find_conflicts(
        self,
        jira_changes: Dict[str, Dict[str, Any]],
        gcal_changes: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Find fields that changed in both systems.

        Returns:
            Dict of field_name -> {jira_value, gcal_value}
        """
        conflicts = {}

        jira_fields = set(jira_changes.keys())
        gcal_fields = set(gcal_changes.keys())
        overlapping = jira_fields & gcal_fields

        for field in overlapping:
            jira_value = jira_changes[field].get('new_value')
            gcal_value = gcal_changes[field].get('new_value')

            # Only conflict if values are actually different
            if jira_value != gcal_value:
                conflicts[field] = {
                    'jira_value': jira_value,
                    'gcal_value': gcal_value
                }

        return conflicts
