from typing import Any
from .jira_client import JiraClient

class ConflictHandler:
    """Handles sync conflicts by creating Jira comments and labels."""

    CONFLICT_LABEL = 'sync-conflict'

    def __init__(self, jira_client: JiraClient):
        self.jira_client = jira_client

    def _format_field_name(self, field_name: str) -> str:
        """Convert field_name to human-readable format."""
        return field_name.replace('_', ' ').capitalize()

    def format_conflict_comment(
        self,
        field_name: str,
        jira_value: Any,
        gcal_value: Any
    ) -> str:
        """Format a conflict notification comment."""
        display_name = self._format_field_name(field_name)

        return (
            f"Sync Conflict: {display_name} was changed in both Jira and Google Calendar.\n\n"
            f"• Jira value: {jira_value}\n"
            f"• Calendar value: {gcal_value}\n\n"
            f"→ Edit the {display_name.lower()} field to the correct value to resolve."
        )

    def create_conflict_in_jira(
        self,
        issue_key: str,
        field_name: str,
        jira_value: Any,
        gcal_value: Any
    ) -> None:
        """Create a conflict comment and add label in Jira."""
        comment = self.format_conflict_comment(field_name, jira_value, gcal_value)
        self.jira_client.add_comment(issue_key, comment)
        self.jira_client.add_label(issue_key, self.CONFLICT_LABEL)

    def resolve_conflict_in_jira(self, issue_key: str) -> None:
        """Remove conflict label and add resolution comment."""
        self.jira_client.remove_label(issue_key, self.CONFLICT_LABEL)
        self.jira_client.add_comment(
            issue_key,
            "Sync conflict resolved. Changes have been synchronized."
        )
