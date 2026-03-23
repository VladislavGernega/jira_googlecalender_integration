import uuid
from django.db import models
from django.conf import settings
from .encryption import TokenEncryptor

class JiraUser(models.Model):
    """Stores Jira user info and their Google OAuth credentials."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_account_id = models.CharField(max_length=128, unique=True)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=255)
    google_credentials_encrypted = models.TextField(blank=True)
    google_calendar_id = models.CharField(max_length=255, blank=True)
    team_calendar_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jira_users'

    def __str__(self):
        return f"{self.display_name} ({self.email})"

    def set_google_credentials(self, credentials_json: str):
        """Encrypt and store Google OAuth credentials."""
        if settings.ENCRYPTION_KEY:
            encryptor = TokenEncryptor(settings.ENCRYPTION_KEY)
            self.google_credentials_encrypted = encryptor.encrypt(credentials_json)
        else:
            raise ValueError("ENCRYPTION_KEY not configured")

    def get_google_credentials(self) -> str:
        """Decrypt and return Google OAuth credentials."""
        if not self.google_credentials_encrypted:
            return ''
        if settings.ENCRYPTION_KEY:
            encryptor = TokenEncryptor(settings.ENCRYPTION_KEY)
            return encryptor.decrypt(self.google_credentials_encrypted)
        raise ValueError("ENCRYPTION_KEY not configured")


class Tag(models.Model):
    """Dynamic tags with color coding for calendar events."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color_hex = models.CharField(max_length=7, default='#808080')
    google_color_id = models.IntegerField(default=8)  # Google Calendar color ID (1-11)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tags'

    def __str__(self):
        return self.name


class SyncConfig(models.Model):
    """Configuration for which Jira issues sync to calendars."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_project_key = models.CharField(max_length=50)
    issue_types = models.JSONField(default=list)  # ["Task", "Story"]
    sync_to_team_calendar = models.BooleanField(default=False)
    team_calendar_id = models.CharField(max_length=255, blank=True)
    additional_jql = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sync_configs'

    def __str__(self):
        return f"{self.jira_project_key} sync config"


class SyncedIssue(models.Model):
    """Links a Jira issue to its Google Calendar event(s)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_issue_key = models.CharField(max_length=50)
    jira_issue_id = models.CharField(max_length=50)
    google_event_id = models.CharField(max_length=255)
    team_event_id = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(JiraUser, on_delete=models.CASCADE, related_name='synced_issues')
    last_jira_update = models.DateTimeField(null=True, blank=True)
    last_gcal_update = models.DateTimeField(null=True, blank=True)
    is_personal = models.BooleanField(default=False)
    sync_enabled = models.BooleanField(default=True)
    field_checksums = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'synced_issues'
        unique_together = [['jira_issue_key', 'user']]

    def __str__(self):
        return f"{self.jira_issue_key} -> {self.google_event_id}"


class SyncHistory(models.Model):
    """Audit log of all sync activity."""
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
    ]
    SOURCE_CHOICES = [
        ('jira', 'Jira'),
        ('gcal', 'Google Calendar'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    synced_issue = models.ForeignKey(SyncedIssue, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    field_changes = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    conflict_detected = models.BooleanField(default=False)

    class Meta:
        db_table = 'sync_history'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.synced_issue.jira_issue_key} {self.action} from {self.source}"


class Conflict(models.Model):
    """Tracks same-field conflicts for resolution."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('resolved', 'Resolved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    synced_issue = models.ForeignKey(SyncedIssue, on_delete=models.CASCADE, related_name='conflicts')
    field_name = models.CharField(max_length=50)
    jira_value = models.TextField()
    gcal_value = models.TextField()
    jira_timestamp = models.DateTimeField()
    gcal_timestamp = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    resolved_value = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conflicts'

    def __str__(self):
        return f"Conflict: {self.synced_issue.jira_issue_key}.{self.field_name}"
