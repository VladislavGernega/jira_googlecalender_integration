# Jira-Google Calendar Two-Way Sync Service

**Date:** 2026-03-23
**Status:** Approved

## Overview

A self-hosted Django service that provides bidirectional synchronization between Jira Cloud and Google Calendar. All users within a Jira space will have their due dates and task details automatically synced to their Google Calendar, with changes in either system reflected in the other.

## Goals

- Two-way sync between Jira Cloud issues and Google Calendar events
- Support both individual user calendars and shared team calendars
- Dynamic tagging system with color coding (PM, Repair, etc.)
- Conflict detection with Jira-native resolution (no worker access to admin)
- Full audit history of all sync activity
- Minimal user interaction after initial setup
- Stay within free API tier limits

## Non-Goals

- Custom frontend UI (Django Admin only for IT)
- Real-time webhooks (polling-based approach)
- Mobile app
- Jira Server/Data Center support (Cloud only)

## Architecture

### Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Framework | Django 4.x | Admin UI, OAuth, API, models |
| Task Queue | Celery | Async task execution |
| Scheduler | Celery Beat | 30-second sync interval |
| Message Broker | Redis | Task queue for Celery |
| Database | MySQL 8.0 | Data persistence |
| Deployment | Docker Compose | Container orchestration |

### Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Docker Compose Network (internal)                               │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Django    │  │   Celery    │  │   Celery    │             │
│  │    App      │  │   Worker    │  │    Beat     │             │
│  │   :8000     │  │             │  │             │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┴────────────────┘                     │
│                          │                                      │
│              ┌───────────┴───────────┐                          │
│              │                       │                          │
│        ┌─────┴─────┐          ┌──────┴──────┐                   │
│        │   Redis   │          │    MySQL    │                   │
│        │   :6379   │          │    :3306    │                   │
│        └───────────┘          └─────────────┘                   │
│                                                                 │
│  Only Django :8000 exposed to host machine                      │
└─────────────────────────────────────────────────────────────────┘
```

### External Integrations

| Service | Authentication | API |
|---------|----------------|-----|
| Jira Cloud | API Token (single admin token) | REST API v3 |
| Google Calendar | OAuth 2.0 (per-user) | Calendar API v3 |

## Data Models

### JiraUser

Stores user information and Google OAuth credentials.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| jira_account_id | String | Jira user account ID |
| email | String | User email (links Jira to Google) |
| display_name | String | User's display name |
| google_credentials | EncryptedText | OAuth refresh token (AES encrypted) |
| google_calendar_id | String | User's primary calendar ID |
| team_calendar_id | String | Shared team calendar ID (nullable) |
| is_active | Boolean | Whether sync is enabled |
| created_at | DateTime | Account creation timestamp |

### SyncedIssue

Links a Jira issue to its Google Calendar event(s).

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| jira_issue_key | String | e.g., "MAINT-123" |
| jira_issue_id | String | Jira's internal issue ID |
| google_event_id | String | Individual calendar event ID |
| team_event_id | String | Team calendar event ID (nullable) |
| user | FK(JiraUser) | Assigned user |
| last_jira_update | DateTime | Last Jira modification timestamp |
| last_gcal_update | DateTime | Last Google Calendar modification |
| is_personal | Boolean | Personal task vs team assignment |
| sync_enabled | Boolean | Whether this issue syncs |
| field_checksums | JSON | Hash of each field for change detection |

### Tag

Dynamic, reusable tags with color coding.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | String | Tag name (unique), e.g., "PM" |
| color_hex | String | Hex color, e.g., "#4CAF50" |
| google_color_id | Integer | Google Calendar color ID (1-11) |
| created_at | DateTime | Creation timestamp |

Default tags:
- PM (Preventative Maintenance) → Green (#4CAF50)
- Repair → Red (#F44336)
- Installation → Blue (#2196F3)
- Inspection → Yellow (#FFEB3B)

### SyncHistory

Audit log of all sync activity.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| synced_issue | FK(SyncedIssue) | Related issue |
| action | Enum | created, updated, deleted |
| source | Enum | jira, gcal |
| field_changes | JSON | {"field": {"old": x, "new": y}} |
| timestamp | DateTime | When action occurred |
| conflict_detected | Boolean | Whether this triggered a conflict |

### SyncConfig

Defines which Jira issues sync.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| jira_project_key | String | e.g., "MAINT" |
| issue_types | JSON | ["Task", "Story", "Sub-task"] |
| sync_to_team_calendar | Boolean | Also sync to team calendar |
| team_calendar_id | String | Team calendar ID |
| additional_jql | String | Extra filter, e.g., "priority = High" |
| is_active | Boolean | Whether config is active |

### Conflict

Tracks same-field conflicts for resolution.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| synced_issue | FK(SyncedIssue) | Related issue |
| field_name | String | e.g., "due_date" |
| jira_value | Text | Value from Jira |
| gcal_value | Text | Value from Google Calendar |
| jira_timestamp | DateTime | When Jira changed |
| gcal_timestamp | DateTime | When Calendar changed |
| status | Enum | pending, resolved |
| resolved_value | Text | Final value chosen |
| resolved_at | DateTime | Resolution timestamp |

## Sync Logic

### Polling Cycle (Every 30 Seconds)

```
Phase 1: Fetch Changes
├── Query Jira for issues updated since last sync
│   └── JQL: "project IN (...) AND updated >= -1m AND duedate IS NOT EMPTY"
└── Query Google Calendar for events updated since last sync
    └── For each user calendar + team calendars

Phase 2: Detect Changes
├── Compare field checksums for each synced issue
├── Determine change direction:
│   ├── No changes → Skip
│   ├── Jira only → Push to Google Calendar
│   ├── Google only → Push to Jira
│   ├── Both (different fields) → Merge bidirectionally
│   └── Both (same field) → Create Conflict

Phase 3: Apply Updates
├── Update Jira via REST API
├── Update Google Calendar via Calendar API
├── Parse [TAG] from event title changes
├── Update field_checksums
└── Log to SyncHistory

Phase 4: Handle New/Deleted Items
├── New Jira issue → Create calendar event + notify
├── Deleted Jira issue → Delete calendar event + archive
└── Deleted calendar event → Delete Jira issue + archive
```

### Field Mapping

| Jira Field | Google Calendar Field | Sync Direction |
|------------|----------------------|----------------|
| Summary | Event title (after tag) | Bidirectional |
| Due date | Event start time (8:00 AM) | Bidirectional |
| Description | Event description (partial) | Bidirectional |
| Labels (first) | Title prefix [TAG] | Bidirectional |
| Status | Description (read-only) | Jira → Calendar |
| Priority | Description (read-only) | Jira → Calendar |
| Assignee | Calendar target | Jira → Calendar |
| Issue key | Title suffix | Jira → Calendar |
| Issue URL | Description link | Jira → Calendar |

### Conflict Resolution (Jira-Native)

Workers never access Django Admin. Conflicts are resolved in Jira:

1. **Conflict detected:** Same field changed in both systems
2. **Jira comment added:**
   ```
   ⚠️ Sync Conflict: Due date was changed in both Jira and Google Calendar.
   • Jira value: March 28, 2024
   • Calendar value: March 26, 2024
   → Edit the due date field to the correct value to resolve.
   ```
3. **Label added:** `sync-conflict`
4. **User edits field in Jira** to desired value
5. **Next sync cycle:** Detects change, pushes to Calendar
6. **Conflict resolved:** Label removed, confirmation comment added

## Google Calendar Event Format

### Event Structure

```
Title:       [PM] Replace HVAC Filter - MAINT-123
Time:        8:00 AM - 8:30 AM on due date
Color:       Based on tag (PM = green, Repair = red)

Description:
─────────────────────────────────────────────
Status: In Progress
Priority: High
Project: Maintenance
Assignee: John Smith
─────────────────────────────────────────────

Quarterly filter replacement for Building A, Floor 3.
Check inventory before starting.

─────────────────────────────────────────────
🔗 https://yoursite.atlassian.net/browse/MAINT-123
```

### Tag Color Mapping

| Tag | Color | Google Color ID |
|-----|-------|-----------------|
| PM | Green | 10 |
| Repair | Red | 11 |
| Installation | Blue | 9 |
| Inspection | Yellow | 5 |
| (new tags) | Auto-assigned | Next available |

## Notifications

### Notification 1: New Assignment

- **Trigger:** New issue assigned to user syncs for first time
- **When:** Immediately (0-minute reminder on event)
- **Method:** Google Calendar popup notification

### Notification 2: Day-of Reminder

- **Trigger:** Due date is today
- **When:** 8:00 AM on the due date
- **Method:** Event starts at 8:00 AM, Google Calendar notifies at event time

Events are 30-minute blocks at 8:00 AM — visible but not intrusive.

## Security

### Credential Storage

| Credential | Storage | Protection |
|------------|---------|------------|
| Google OAuth tokens | MySQL (encrypted) | Fernet AES-128 encryption |
| Jira API token | Environment variable | Never in database/code |
| Django secret key | Environment variable | Used for session signing |
| MySQL password | Environment variable | Docker-internal only |

### Network Isolation

- Redis and MySQL only accessible within Docker network
- Only Django app exposed to host (localhost:8000)
- All external API calls use HTTPS (TLS 1.2+)

### Environment Variables

```
DJANGO_SECRET_KEY=<random-64-char>
ENCRYPTION_KEY=<fernet-key>
JIRA_API_TOKEN=<token>
JIRA_EMAIL=<admin-email>
JIRA_BASE_URL=https://yoursite.atlassian.net
MYSQL_ROOT_PASSWORD=<strong-password>
MYSQL_PASSWORD=<strong-password>
GOOGLE_CLIENT_ID=<from-gcp-console>
GOOGLE_CLIENT_SECRET=<from-gcp-console>
```

`.env` file is gitignored. `.env.example` provided with placeholders.

## User Setup Flow

### Worker Setup (One-Time)

1. IT shares link: `https://your-server:8000/auth/google/`
2. User clicks → Google OAuth consent screen
3. User allows calendar access
4. User enters Jira email to link accounts
5. Done — sync starts within 30 seconds

User never needs to visit the Django app again.

### IT Admin Setup (One-Time)

Via Django Admin:
1. Configure SyncConfig (projects, issue types)
2. Pre-create common tags with colors
3. Set team calendar ID if using shared calendar

## API Rate Limits & Safeguards

### Google Calendar API

- Free tier: 1,000,000 queries/day
- With incremental sync at 30-second intervals: ~2,880 queries/day per calendar
- Well within limits for typical team sizes

### Jira Cloud API

- Rate limit: ~100 requests/minute
- 30-second polling: ~2 requests/minute
- Exponential backoff on rate limit errors

### Safeguards

- Incremental sync (only fetch changes since last poll)
- Batch operations where possible
- Local caching of user/project data
- Automatic backoff on rate limit responses

## File Structure

```
jira-gcal-sync/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── requirements.txt
├── manage.py
├── config/
│   ├── settings.py
│   ├── celery.py
│   └── urls.py
├── sync/
│   ├── models.py          # Data models
│   ├── admin.py           # Django admin config
│   ├── tasks.py           # Celery sync tasks
│   ├── jira_client.py     # Jira API wrapper
│   ├── gcal_client.py     # Google Calendar API wrapper
│   ├── sync_engine.py     # Core sync logic
│   ├── conflict.py        # Conflict detection/resolution
│   └── encryption.py      # Token encryption utilities
├── auth/
│   ├── views.py           # Google OAuth flow
│   └── urls.py
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-03-23-jira-gcal-sync-design.md
```

## Success Criteria

- [ ] Sync completes within 30-second intervals
- [ ] Changes in Jira appear in Google Calendar within 60 seconds
- [ ] Changes in Google Calendar appear in Jira within 60 seconds
- [ ] Conflicts are flagged in Jira with clear resolution instructions
- [ ] No API rate limit errors under normal operation
- [ ] Full audit trail of all sync activity viewable in Django Admin
- [ ] Docker Compose brings up entire stack with single command
