from django.contrib import admin
from .models import JiraUser, Tag, SyncConfig, SyncedIssue, SyncHistory, Conflict

@admin.register(JiraUser)
class JiraUserAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'email', 'jira_account_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['display_name', 'email', 'jira_account_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'google_credentials_encrypted']

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color_hex', 'google_color_id', 'created_at']
    search_fields = ['name']

@admin.register(SyncConfig)
class SyncConfigAdmin(admin.ModelAdmin):
    list_display = ['jira_project_key', 'issue_types', 'sync_to_team_calendar', 'is_active']
    list_filter = ['is_active', 'sync_to_team_calendar']
    search_fields = ['jira_project_key']

@admin.register(SyncedIssue)
class SyncedIssueAdmin(admin.ModelAdmin):
    list_display = ['jira_issue_key', 'user', 'google_event_id', 'is_personal', 'sync_enabled', 'updated_at']
    list_filter = ['is_personal', 'sync_enabled', 'created_at']
    search_fields = ['jira_issue_key', 'user__email']
    readonly_fields = ['id', 'created_at', 'updated_at']

@admin.register(SyncHistory)
class SyncHistoryAdmin(admin.ModelAdmin):
    list_display = ['synced_issue', 'action', 'source', 'conflict_detected', 'timestamp']
    list_filter = ['action', 'source', 'conflict_detected', 'timestamp']
    search_fields = ['synced_issue__jira_issue_key']
    readonly_fields = ['id', 'timestamp']

@admin.register(Conflict)
class ConflictAdmin(admin.ModelAdmin):
    list_display = ['synced_issue', 'field_name', 'status', 'created_at', 'resolved_at']
    list_filter = ['status', 'field_name', 'created_at']
    search_fields = ['synced_issue__jira_issue_key']
    readonly_fields = ['id', 'created_at']
