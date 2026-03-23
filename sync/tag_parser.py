import re
from typing import Optional, Tuple


class TagParser:
    """Parse and format [TAG] prefixes in calendar event titles."""

    TAG_PATTERN = re.compile(r'^\[([^\]]+)\]\s*')
    ISSUE_KEY_PATTERN = re.compile(r'([A-Z][A-Z0-9]*-\d+)$')

    def parse_title(self, title: str) -> Tuple[Optional[str], str]:
        """Extract tag and clean title from event title.

        Returns:
            Tuple of (tag or None, remaining title)
        """
        match = self.TAG_PATTERN.match(title)
        if match:
            tag = match.group(1)
            remaining = title[match.end():].strip()
            return tag, remaining
        return None, title.strip()

    def format_title(self, tag: Optional[str], summary: str, issue_key: str) -> str:
        """Format title with optional tag prefix and issue key suffix.

        Returns:
            Formatted title like "[PM] Summary - PROJ-123"
        """
        parts = []
        if tag:
            parts.append(f"[{tag}]")
        parts.append(summary)

        title = " ".join(parts)
        return f"{title} - {issue_key}"

    def extract_issue_key(self, title: str) -> Optional[str]:
        """Extract Jira issue key from title suffix.

        Returns:
            Issue key like "PROJ-123" or None
        """
        # Remove tag first
        _, clean_title = self.parse_title(title)
        match = self.ISSUE_KEY_PATTERN.search(clean_title)
        return match.group(1) if match else None
