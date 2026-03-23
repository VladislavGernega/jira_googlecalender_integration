import pytest
from sync.tag_parser import TagParser


class TestTagParser:
    def test_parse_tag_from_title_with_tag(self):
        parser = TagParser()
        tag, title = parser.parse_title("[PM] Replace HVAC Filter - MAINT-123")

        assert tag == "PM"
        assert title == "Replace HVAC Filter - MAINT-123"

    def test_parse_tag_from_title_without_tag(self):
        parser = TagParser()
        tag, title = parser.parse_title("Replace HVAC Filter - MAINT-123")

        assert tag is None
        assert title == "Replace HVAC Filter - MAINT-123"

    def test_parse_tag_case_preserved(self):
        parser = TagParser()
        tag, title = parser.parse_title("[Repair] Fix door - MAINT-456")

        assert tag == "Repair"
        assert title == "Fix door - MAINT-456"

    def test_format_title_with_tag(self):
        parser = TagParser()
        formatted = parser.format_title("PM", "Replace Filter", "MAINT-123")

        assert formatted == "[PM] Replace Filter - MAINT-123"

    def test_format_title_without_tag(self):
        parser = TagParser()
        formatted = parser.format_title(None, "Replace Filter", "MAINT-123")

        assert formatted == "Replace Filter - MAINT-123"

    def test_extract_issue_key_from_title(self):
        parser = TagParser()
        key = parser.extract_issue_key("[PM] Replace Filter - MAINT-123")

        assert key == "MAINT-123"

    def test_extract_issue_key_not_found(self):
        parser = TagParser()
        key = parser.extract_issue_key("Replace Filter")

        assert key is None
