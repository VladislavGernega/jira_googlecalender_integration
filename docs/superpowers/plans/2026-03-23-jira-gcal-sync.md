
# Jira-Google Calendar Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Django service that bidirectionally syncs Jira Cloud issues with Google Calendar events, supporting individual and team calendars with dynamic tagging and Jira-native conflict resolution.

**Architecture:** Django app with Celery workers polling Jira and Google Calendar APIs every 30 seconds. Field-level change detection enables bidirectional sync with automatic merging. MySQL stores sync state, audit history, and encrypted OAuth tokens. Conflicts surface as Jira comments/labels for user resolution.

**Tech Stack:** Python 3.11, Django 4.x, Celery, Redis, MySQL 8.0, Docker Compose, google-api-python-client, requests, cryptography (Fernet)

**Spec:** `docs/superpowers/specs/2026-03-23-jira-gcal-sync-design.md`

---

## File Structure

```
jira-gcal-sync/
├── docker-compose.yml              # Container orchestration
├── Dockerfile                      # Django app image
├── .env.example                    # Environment template
├── .gitignore                      # Git ignores
├── requirements.txt                # Python dependencies
├── manage.py                       # Django CLI
├── config/
│   ├── __init__.py
│   ├── settings.py                 # Django settings
│   ├── celery.py                   # Celery configuration
│   ├── urls.py                     # Root URL routing
│   └── wsgi.py                     # WSGI entry point
├── sync/
│   ├── __init__.py
│   ├── models.py                   # JiraUser, SyncedIssue, Tag, SyncHistory, SyncConfig, Conflict
│   ├── admin.py                    # Django admin configuration
│   ├── encryption.py               # Fernet encryption for OAuth tokens
│   ├── jira_client.py              # Jira REST API wrapper
│   ├── gcal_client.py              # Google Calendar API wrapper
│   ├── sync_engine.py              # Core sync orchestration
│   ├── change_detector.py          # Field-level change detection
│   ├── conflict_handler.py         # Conflict detection and Jira comment creation
│   ├── tag_parser.py               # Parse [TAG] from calendar titles
│   └── tasks.py                    # Celery tasks
├── auth/
│   ├── __init__.py
│   ├── views.py                    # Google OAuth flow
│   └── urls.py                     # Auth URL routing
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures
    ├── test_encryption.py
    ├── test_jira_client.py
    ├── test_gcal_client.py
    ├── test_tag_parser.py
    ├── test_change_detector.py
    ├── test_conflict_handler.py
    ├── test_sync_engine.py
    └── test_tasks.py
```

---

## Task 1: Project Setup and Docker Configuration

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`

- [ ] **Step 1: Create .gitignore**

```gitignore
# Environment
.env
*.env.local

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/

# Django
*.log
local_settings.py
db.sqlite3
media/

# IDE
.idea/
.vscode/
*.swp

# Docker
.docker/

# Superpowers
.superpowers/
```

- [ ] **Step 2: Create .env.example**

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here-min-50-chars-random
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Encryption
ENCRYPTION_KEY=your-fernet-key-here-generate-with-cryptography

# Database
MYSQL_DATABASE=jira_gcal_sync
MYSQL_USER=sync_user
MYSQL_PASSWORD=your-strong-password-here
MYSQL_ROOT_PASSWORD=your-root-password-here
MYSQL_HOST=db
MYSQL_PORT=3306

# Redis
REDIS_URL=redis://redis:6379/0

# Jira
JIRA_BASE_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-admin@email.com
JIRA_API_TOKEN=your-jira-api-token

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback/
```

- [ ] **Step 3: Create requirements.txt**

```txt
Django>=4.2,<5.0
celery>=5.3,<6.0
redis>=5.0,<6.0
mysqlclient>=2.2,<3.0
google-api-python-client>=2.100,<3.0
google-auth-oauthlib>=1.1,<2.0
google-auth-httplib2>=0.1,<1.0
requests>=2.31,<3.0
cryptography>=41.0,<42.0
python-dotenv>=1.0,<2.0
pytest>=7.4,<8.0
pytest-django>=4.5,<5.0
pytest-celery>=0.0,<1.0
```

- [ ] **Step 4: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

- [ ] **Step 5: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery_worker:
    build: .
    command: celery -A config worker -l info
    volumes:
      - .:/app
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery_beat:
    build: .
    command: celery -A config beat -l info
    volumes:
      - .:/app
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  mysql_data:
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example requirements.txt Dockerfile docker-compose.yml
git commit -m "feat: add Docker and project configuration"
```

---

## Task 2: Django Project Initialization

**Files:**
- Create: `manage.py`
- Create: `config/__init__.py`
- Create: `config/settings.py`
- Create: `config/urls.py`
- Create: `config/wsgi.py`
- Create: `config/celery.py`

- [ ] **Step 1: Create manage.py**

```python
#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Create config/__init__.py**

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

- [ ] **Step 3: Create config/settings.py**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'sync',
    'auth',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_DATABASE', 'jira_gcal_sync'),
        'USER': os.environ.get('MYSQL_USER', 'sync_user'),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
        'HOST': os.environ.get('MYSQL_HOST', 'db'),
        'PORT': os.environ.get('MYSQL_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Encryption key for OAuth tokens
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')

# Jira configuration
JIRA_BASE_URL = os.environ.get('JIRA_BASE_URL', '')
JIRA_EMAIL = os.environ.get('JIRA_EMAIL', '')
JIRA_API_TOKEN = os.environ.get('JIRA_API_TOKEN', '')

# Google OAuth
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:8000/auth/google/callback/')
```

- [ ] **Step 4: Create config/celery.py**

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('jira_gcal_sync')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Schedule sync task every 30 seconds
app.conf.beat_schedule = {
    'sync-jira-gcal-every-30-seconds': {
        'task': 'sync.tasks.run_sync',
        'schedule': 30.0,
    },
}
```

- [ ] **Step 5: Create config/urls.py**

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('auth.urls')),
]
```

- [ ] **Step 6: Create config/wsgi.py**

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
```

- [ ] **Step 7: Commit**

```bash
git add manage.py config/
git commit -m "feat: initialize Django project with Celery configuration"
```

---

## Task 3: Encryption Module

**Files:**
- Create: `sync/__init__.py`
- Create: `sync/encryption.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_encryption.py`

- [ ] **Step 1: Create sync/__init__.py**

```python
default_app_config = 'sync.apps.SyncConfig'
```

- [ ] **Step 2: Create tests/__init__.py**

```python
# Tests package
```

- [ ] **Step 3: Create tests/conftest.py**

```python
import pytest
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

@pytest.fixture(scope='session')
def django_db_setup():
    pass

@pytest.fixture
def encryption_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
```

- [ ] **Step 4: Write the failing test for encryption**

```python
# tests/test_encryption.py
import pytest
from sync.encryption import TokenEncryptor

class TestTokenEncryptor:
    def test_encrypt_decrypt_roundtrip(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)
        original = '{"access_token": "secret123", "refresh_token": "refresh456"}'

        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original

    def test_encrypted_value_is_different_each_time(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)
        original = 'test-token'

        encrypted1 = encryptor.encrypt(original)
        encrypted2 = encryptor.encrypt(original)

        # Fernet includes timestamp, so same plaintext produces different ciphertext
        assert encrypted1 != encrypted2

    def test_decrypt_invalid_token_raises_error(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)

        with pytest.raises(Exception):
            encryptor.decrypt('invalid-not-base64-fernet-token')
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/test_encryption.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.encryption'"

- [ ] **Step 6: Write minimal implementation**

```python
# sync/encryption.py
from cryptography.fernet import Fernet, InvalidToken

class TokenEncryptor:
    """Encrypts and decrypts OAuth tokens using Fernet (AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, key: str):
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return base64-encoded ciphertext."""
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext and return plaintext."""
        try:
            return self.fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise ValueError("Invalid or corrupted token") from e
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_encryption.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add sync/__init__.py sync/encryption.py tests/
git commit -m "feat: add token encryption module with Fernet"
```

---

## Task 4: Data Models

**Files:**
- Create: `sync/models.py`
- Create: `sync/apps.py`

- [ ] **Step 1: Create sync/apps.py**

```python
from django.apps import AppConfig

class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'
```

- [ ] **Step 2: Create sync/models.py**

```python
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
```

- [ ] **Step 3: Create migrations**

Run: `python manage.py makemigrations sync`
Expected: Creates migration file in sync/migrations/

- [ ] **Step 4: Commit**

```bash
git add sync/apps.py sync/models.py sync/migrations/
git commit -m "feat: add data models for sync service"
```

---

## Task 5: Django Admin Configuration

**Files:**
- Create: `sync/admin.py`

- [ ] **Step 1: Create sync/admin.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add sync/admin.py
git commit -m "feat: add Django admin configuration for all models"
```

---

## Task 6: Tag Parser Module

**Files:**
- Create: `sync/tag_parser.py`
- Create: `tests/test_tag_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tag_parser.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tag_parser.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.tag_parser'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/tag_parser.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tag_parser.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/tag_parser.py tests/test_tag_parser.py
git commit -m "feat: add tag parser for calendar event titles"
```

---

## Task 7: Jira Client Module

**Files:**
- Create: `sync/jira_client.py`
- Create: `tests/test_jira_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jira_client.py
import pytest
from unittest.mock import Mock, patch
from sync.jira_client import JiraClient

class TestJiraClient:
    @pytest.fixture
    def client(self):
        return JiraClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token"
        )

    def test_build_auth_header(self, client):
        headers = client._build_headers()

        assert 'Authorization' in headers
        assert headers['Authorization'].startswith('Basic ')
        assert headers['Content-Type'] == 'application/json'

    @patch('sync.jira_client.requests.get')
    def test_get_issues_updated_since(self, mock_get, client):
        mock_response = Mock()
        mock_response.json.return_value = {
            'issues': [
                {
                    'key': 'TEST-1',
                    'id': '10001',
                    'fields': {
                        'summary': 'Test issue',
                        'duedate': '2024-03-25',
                        'assignee': {'accountId': 'user123', 'displayName': 'John'},
                        'status': {'name': 'In Progress'},
                        'priority': {'name': 'High'},
                        'labels': ['PM'],
                        'description': 'Test description',
                        'updated': '2024-03-20T10:00:00.000+0000'
                    }
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        issues = client.get_issues_updated_since(
            projects=['TEST'],
            issue_types=['Task'],
            since_minutes=5
        )

        assert len(issues) == 1
        assert issues[0]['key'] == 'TEST-1'

    @patch('sync.jira_client.requests.put')
    def test_update_issue(self, mock_put, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        client.update_issue('TEST-1', {'summary': 'Updated title'})

        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert 'TEST-1' in call_args[0][0]

    @patch('sync.jira_client.requests.post')
    def test_add_comment(self, mock_post, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client.add_comment('TEST-1', 'Sync conflict detected')

        mock_post.assert_called_once()

    @patch('sync.jira_client.requests.put')
    def test_add_label(self, mock_put, client):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        client.add_label('TEST-1', 'sync-conflict')

        mock_put.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jira_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.jira_client'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/jira_client.py
import base64
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class JiraClient:
    """Wrapper for Jira Cloud REST API."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.api_token = api_token

    def _build_headers(self) -> Dict[str, str]:
        """Build authentication headers for Jira API."""
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def get_issues_updated_since(
        self,
        projects: List[str],
        issue_types: List[str],
        since_minutes: int = 5,
        additional_jql: str = ''
    ) -> List[Dict[str, Any]]:
        """Fetch issues updated since given time with due dates."""
        project_jql = f"project IN ({','.join(projects)})"
        type_jql = f"issuetype IN ({','.join(issue_types)})"
        time_jql = f"updated >= -{since_minutes}m"
        due_jql = "duedate IS NOT EMPTY"

        jql_parts = [project_jql, type_jql, time_jql, due_jql]
        if additional_jql:
            jql_parts.append(f"({additional_jql})")

        jql = " AND ".join(jql_parts)

        url = f"{self.base_url}/rest/api/3/search"
        params = {
            'jql': jql,
            'fields': 'summary,duedate,assignee,status,priority,labels,description,updated'
        }

        response = requests.get(url, headers=self._build_headers(), params=params)
        response.raise_for_status()
        return response.json().get('issues', [])

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Fetch a single issue by key."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        params = {
            'fields': 'summary,duedate,assignee,status,priority,labels,description,updated'
        }

        response = requests.get(url, headers=self._build_headers(), params=params)
        response.raise_for_status()
        return response.json()

    def update_issue(self, issue_key: str, fields: Dict[str, Any]) -> None:
        """Update issue fields."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {'fields': fields}

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def add_comment(self, issue_key: str, body: str) -> None:
        """Add a comment to an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        data = {
            'body': {
                'type': 'doc',
                'version': 1,
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [{'type': 'text', 'text': body}]
                    }
                ]
            }
        }

        response = requests.post(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def add_label(self, issue_key: str, label: str) -> None:
        """Add a label to an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {
            'update': {
                'labels': [{'add': label}]
            }
        }

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def remove_label(self, issue_key: str, label: str) -> None:
        """Remove a label from an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {
            'update': {
                'labels': [{'remove': label}]
            }
        }

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def delete_issue(self, issue_key: str) -> None:
        """Delete an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"

        response = requests.delete(url, headers=self._build_headers())
        response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_jira_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/jira_client.py tests/test_jira_client.py
git commit -m "feat: add Jira REST API client"
```

---

## Task 8: Google Calendar Client Module

**Files:**
- Create: `sync/gcal_client.py`
- Create: `tests/test_gcal_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gcal_client.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from sync.gcal_client import GoogleCalendarClient

class TestGoogleCalendarClient:
    @pytest.fixture
    def mock_credentials(self):
        return {
            'token': 'access-token',
            'refresh_token': 'refresh-token',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'client-id',
            'client_secret': 'client-secret'
        }

    @pytest.fixture
    def client(self, mock_credentials):
        with patch('sync.gcal_client.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            return GoogleCalendarClient(mock_credentials)

    def test_create_event(self, client):
        client.service.events().insert().execute.return_value = {
            'id': 'event123',
            'summary': '[PM] Test Task - TEST-1'
        }

        event_id = client.create_event(
            calendar_id='primary',
            summary='Test Task',
            due_date=datetime(2024, 3, 25),
            description='Test description',
            tag='PM',
            issue_key='TEST-1',
            issue_url='https://test.atlassian.net/browse/TEST-1',
            color_id=10
        )

        assert event_id == 'event123'

    def test_update_event(self, client):
        client.service.events().update().execute.return_value = {'id': 'event123'}

        client.update_event(
            calendar_id='primary',
            event_id='event123',
            summary='Updated Task',
            due_date=datetime(2024, 3, 26)
        )

        client.service.events().update.assert_called()

    def test_delete_event(self, client):
        client.service.events().delete().execute.return_value = None

        client.delete_event(calendar_id='primary', event_id='event123')

        client.service.events().delete.assert_called()

    def test_get_events_updated_since(self, client):
        client.service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': '[PM] Task 1 - TEST-1',
                    'updated': '2024-03-20T10:00:00Z'
                }
            ]
        }

        events = client.get_events_updated_since(
            calendar_id='primary',
            since=datetime(2024, 3, 20)
        )

        assert len(events) == 1
        assert events[0]['id'] == 'event1'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gcal_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.gcal_client'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/gcal_client.py
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GoogleCalendarClient:
    """Wrapper for Google Calendar API."""

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, credentials_dict: Dict[str, Any]):
        """Initialize with credentials dictionary."""
        self.credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=self.SCOPES
        )
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        due_date: datetime,
        description: str,
        tag: Optional[str],
        issue_key: str,
        issue_url: str,
        color_id: int = 8,
        status: str = '',
        priority: str = '',
        assignee: str = ''
    ) -> str:
        """Create a calendar event and return event ID."""
        # Format title with tag
        title = f"[{tag}] {summary} - {issue_key}" if tag else f"{summary} - {issue_key}"

        # Build description with metadata
        desc_parts = []
        if status:
            desc_parts.append(f"Status: {status}")
        if priority:
            desc_parts.append(f"Priority: {priority}")
        if assignee:
            desc_parts.append(f"Assignee: {assignee}")
        if desc_parts:
            desc_parts.append("─" * 40)
        if description:
            desc_parts.append(description)
        desc_parts.append("─" * 40)
        desc_parts.append(f"🔗 {issue_url}")

        full_description = "\n".join(desc_parts)

        # Event at 8:00 AM on due date, 30 min duration
        start_time = due_date.replace(hour=8, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(minutes=30)

        event = {
            'summary': title,
            'description': full_description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'colorId': str(color_id),
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 0},  # At event time (8 AM)
                ],
            },
        }

        result = self.service.events().insert(calendarId=calendar_id, body=event).execute()
        return result['id']

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        summary: Optional[str] = None,
        due_date: Optional[datetime] = None,
        description: Optional[str] = None,
        color_id: Optional[int] = None
    ) -> None:
        """Update an existing calendar event."""
        # Get current event
        event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if summary is not None:
            event['summary'] = summary

        if due_date is not None:
            start_time = due_date.replace(hour=8, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(minutes=30)
            event['start'] = {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'}
            event['end'] = {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'}

        if description is not None:
            event['description'] = description

        if color_id is not None:
            event['colorId'] = str(color_id)

        self.service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete a calendar event."""
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    def get_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
        """Get a single event by ID."""
        return self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    def get_events_updated_since(
        self,
        calendar_id: str,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """Get events updated since given time."""
        updated_min = since.isoformat() + 'Z'

        result = self.service.events().list(
            calendarId=calendar_id,
            updatedMin=updated_min,
            singleEvents=True,
            orderBy='updated'
        ).execute()

        return result.get('items', [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gcal_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/gcal_client.py tests/test_gcal_client.py
git commit -m "feat: add Google Calendar API client"
```

---

## Task 9: Change Detector Module

**Files:**
- Create: `sync/change_detector.py`
- Create: `tests/test_change_detector.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_change_detector.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_change_detector.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.change_detector'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/change_detector.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_change_detector.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/change_detector.py tests/test_change_detector.py
git commit -m "feat: add field-level change detector"
```

---

## Task 10: Conflict Handler Module

**Files:**
- Create: `sync/conflict_handler.py`
- Create: `tests/test_conflict_handler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_conflict_handler.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_conflict_handler.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.conflict_handler'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/conflict_handler.py
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
            f"⚠️ Sync Conflict: {display_name} was changed in both Jira and Google Calendar.\n\n"
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
            "✓ Sync conflict resolved. Changes have been synchronized."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_conflict_handler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/conflict_handler.py tests/test_conflict_handler.py
git commit -m "feat: add Jira-native conflict handler"
```

---

## Task 11: Google OAuth Flow

**Files:**
- Create: `auth/__init__.py`
- Create: `auth/urls.py`
- Create: `auth/views.py`

- [ ] **Step 1: Create auth/__init__.py**

```python
# Auth app
```

- [ ] **Step 2: Create auth/urls.py**

```python
from django.urls import path
from . import views

app_name = 'auth'

urlpatterns = [
    path('google/', views.google_oauth_start, name='google_start'),
    path('google/callback/', views.google_oauth_callback, name='google_callback'),
]
```

- [ ] **Step 3: Create auth/views.py**

```python
import json
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse, HttpRequest
from google_auth_oauthlib.flow import Flow

from sync.models import JiraUser

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_oauth_flow(request: HttpRequest) -> Flow:
    """Create OAuth flow with Google credentials."""
    client_config = {
        'web': {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [settings.GOOGLE_REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow

def google_oauth_start(request: HttpRequest) -> HttpResponse:
    """Start Google OAuth flow."""
    flow = get_oauth_flow(request)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    request.session['oauth_state'] = state
    return redirect(authorization_url)

def google_oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle Google OAuth callback."""
    state = request.session.get('oauth_state')

    if not state:
        return HttpResponse("Missing OAuth state", status=400)

    flow = get_oauth_flow(request)
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    credentials_dict = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
    }

    # Store in session for linking step
    request.session['google_credentials'] = json.dumps(credentials_dict)

    return HttpResponse(
        """
        <html>
        <body>
            <h1>Google Calendar Connected!</h1>
            <p>Enter your Jira email to link your account:</p>
            <form method="POST" action="/auth/google/link/">
                <input type="email" name="email" placeholder="your-jira@email.com" required>
                <button type="submit">Link Account</button>
            </form>
        </body>
        </html>
        """,
        content_type='text/html'
    )
```

- [ ] **Step 4: Add link endpoint to auth/views.py**

Append to auth/views.py:

```python
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@require_POST
def google_oauth_link(request: HttpRequest) -> HttpResponse:
    """Link Google credentials to Jira user by email."""
    email = request.POST.get('email', '').strip()
    credentials_json = request.session.get('google_credentials')

    if not email:
        return HttpResponse("Email required", status=400)

    if not credentials_json:
        return HttpResponse("No Google credentials in session. Please start OAuth flow again.", status=400)

    try:
        user = JiraUser.objects.get(email=email)
    except JiraUser.DoesNotExist:
        # Create new user record
        user = JiraUser.objects.create(
            email=email,
            jira_account_id='',  # Will be populated on first sync
            display_name=email.split('@')[0],
            google_calendar_id='primary'
        )

    user.set_google_credentials(credentials_json)
    user.is_active = True
    user.save()

    # Clear session
    del request.session['google_credentials']

    return HttpResponse(
        f"""
        <html>
        <body>
            <h1>Account Linked!</h1>
            <p>Your Google Calendar is now connected for {email}.</p>
            <p>Sync will begin within 30 seconds.</p>
        </body>
        </html>
        """,
        content_type='text/html'
    )
```

- [ ] **Step 5: Update auth/urls.py**

```python
from django.urls import path
from . import views

app_name = 'auth'

urlpatterns = [
    path('google/', views.google_oauth_start, name='google_start'),
    path('google/callback/', views.google_oauth_callback, name='google_callback'),
    path('google/link/', views.google_oauth_link, name='google_link'),
]
```

- [ ] **Step 6: Fix config/settings.py INSTALLED_APPS**

Update `INSTALLED_APPS` to use string instead of conflicting import:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'sync',
    'auth_app',  # Renamed to avoid conflict with django.contrib.auth
]
```

Note: Rename `auth/` directory to `auth_app/` to avoid conflict with Django's built-in auth module.

- [ ] **Step 7: Rename auth to auth_app**

Run:
```bash
mv auth auth_app
```

Update all imports from `auth` to `auth_app`.

- [ ] **Step 8: Commit**

```bash
git add auth_app/ config/settings.py config/urls.py
git commit -m "feat: add Google OAuth flow for user authentication"
```

---

## Task 12: Sync Engine Module

**Files:**
- Create: `sync/sync_engine.py`
- Create: `tests/test_sync_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sync_engine.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from sync.sync_engine import SyncEngine

class TestSyncEngine:
    @pytest.fixture
    def mock_jira_client(self):
        return Mock()

    @pytest.fixture
    def mock_gcal_client_factory(self):
        return Mock(return_value=Mock())

    @pytest.fixture
    def engine(self, mock_jira_client, mock_gcal_client_factory):
        return SyncEngine(mock_jira_client, mock_gcal_client_factory)

    def test_extract_jira_fields(self, engine):
        jira_issue = {
            'key': 'TEST-1',
            'id': '10001',
            'fields': {
                'summary': 'Test Task',
                'duedate': '2024-03-25',
                'description': {'content': [{'content': [{'text': 'Desc'}]}]},
                'status': {'name': 'In Progress'},
                'priority': {'name': 'High'},
                'labels': ['PM', 'urgent'],
                'assignee': {'accountId': 'user123', 'displayName': 'John', 'emailAddress': 'john@test.com'},
                'updated': '2024-03-20T10:00:00.000+0000'
            }
        }

        fields = engine.extract_jira_fields(jira_issue)

        assert fields['summary'] == 'Test Task'
        assert fields['due_date'] == '2024-03-25'
        assert fields['tag'] == 'PM'
        assert fields['status'] == 'In Progress'
        assert fields['assignee_email'] == 'john@test.com'

    def test_extract_gcal_fields(self, engine):
        gcal_event = {
            'id': 'event123',
            'summary': '[PM] Test Task - TEST-1',
            'start': {'dateTime': '2024-03-25T08:00:00Z'},
            'description': 'Status: In Progress\nPriority: High\n──────\nDesc\n──────\n🔗 https://test.atlassian.net/browse/TEST-1',
            'updated': '2024-03-20T10:00:00Z'
        }

        fields = engine.extract_gcal_fields(gcal_event)

        assert fields['summary'] == 'Test Task'
        assert fields['tag'] == 'PM'
        assert fields['issue_key'] == 'TEST-1'

    def test_should_sync_issue_with_matching_config(self, engine):
        issue = {'key': 'TEST-1', 'fields': {'issuetype': {'name': 'Task'}}}
        config = Mock(jira_project_key='TEST', issue_types=['Task'], is_active=True)

        with patch('sync.sync_engine.SyncConfig.objects') as mock_qs:
            mock_qs.filter.return_value = [config]

            result = engine.should_sync_issue(issue)

        assert result is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_engine.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.sync_engine'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/sync_engine.py
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from django.utils import timezone

from .models import JiraUser, SyncedIssue, SyncConfig, SyncHistory, Tag, Conflict
from .jira_client import JiraClient
from .gcal_client import GoogleCalendarClient
from .tag_parser import TagParser
from .change_detector import ChangeDetector
from .conflict_handler import ConflictHandler

class SyncEngine:
    """Orchestrates bidirectional sync between Jira and Google Calendar."""

    def __init__(
        self,
        jira_client: JiraClient,
        gcal_client_factory: Callable[[Dict], GoogleCalendarClient]
    ):
        self.jira_client = jira_client
        self.gcal_client_factory = gcal_client_factory
        self.tag_parser = TagParser()
        self.change_detector = ChangeDetector()
        self.conflict_handler = ConflictHandler(jira_client)

    def extract_jira_fields(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from Jira issue."""
        fields = issue.get('fields', {})

        # Extract description text
        description = ''
        desc_field = fields.get('description')
        if desc_field and isinstance(desc_field, dict):
            # Atlassian Document Format
            try:
                content = desc_field.get('content', [])
                texts = []
                for block in content:
                    for item in block.get('content', []):
                        if item.get('type') == 'text':
                            texts.append(item.get('text', ''))
                description = '\n'.join(texts)
            except (KeyError, TypeError):
                description = str(desc_field)
        elif desc_field:
            description = str(desc_field)

        # Extract assignee info
        assignee = fields.get('assignee') or {}

        # Get first label as tag
        labels = fields.get('labels', [])
        tag = labels[0] if labels else None

        return {
            'key': issue.get('key'),
            'id': issue.get('id'),
            'summary': fields.get('summary', ''),
            'due_date': fields.get('duedate'),
            'description': description,
            'status': fields.get('status', {}).get('name', ''),
            'priority': fields.get('priority', {}).get('name', ''),
            'tag': tag,
            'labels': labels,
            'assignee_id': assignee.get('accountId'),
            'assignee_name': assignee.get('displayName', ''),
            'assignee_email': assignee.get('emailAddress', ''),
            'updated': fields.get('updated'),
            'project_key': issue.get('key', '').split('-')[0]
        }

    def extract_gcal_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from Google Calendar event."""
        summary = event.get('summary', '')
        tag, clean_title = self.tag_parser.parse_title(summary)
        issue_key = self.tag_parser.extract_issue_key(summary)

        # Remove issue key from title to get just the summary
        if issue_key:
            clean_title = clean_title.replace(f' - {issue_key}', '').strip()

        # Parse due date from start time
        start = event.get('start', {})
        start_dt = start.get('dateTime') or start.get('date')
        due_date = None
        if start_dt:
            try:
                if 'T' in start_dt:
                    due_date = start_dt.split('T')[0]
                else:
                    due_date = start_dt
            except (ValueError, IndexError):
                pass

        # Extract description (without metadata)
        full_desc = event.get('description', '')
        # Find content between the separator lines
        parts = full_desc.split('─' * 40)
        description = parts[1].strip() if len(parts) > 2 else ''

        return {
            'event_id': event.get('id'),
            'summary': clean_title,
            'tag': tag,
            'issue_key': issue_key,
            'due_date': due_date,
            'description': description,
            'updated': event.get('updated')
        }

    def should_sync_issue(self, issue: Dict[str, Any]) -> bool:
        """Check if issue matches any active sync config."""
        project_key = issue.get('key', '').split('-')[0]
        issue_type = issue.get('fields', {}).get('issuetype', {}).get('name')

        configs = SyncConfig.objects.filter(
            jira_project_key=project_key,
            is_active=True
        )

        for config in configs:
            if issue_type in config.issue_types:
                return True

        return False

    def get_or_create_tag(self, tag_name: str) -> Tag:
        """Get existing tag or create new one with auto-assigned color."""
        tag, created = Tag.objects.get_or_create(
            name=tag_name,
            defaults={
                'color_hex': '#808080',
                'google_color_id': 8
            }
        )
        return tag

    def sync_jira_to_gcal(
        self,
        user: JiraUser,
        jira_issue: Dict[str, Any],
        synced_issue: Optional[SyncedIssue] = None
    ) -> SyncedIssue:
        """Sync a Jira issue to Google Calendar."""
        fields = self.extract_jira_fields(jira_issue)
        credentials = json.loads(user.get_google_credentials())
        gcal_client = self.gcal_client_factory(credentials)

        # Get tag color
        color_id = 8
        if fields['tag']:
            tag = self.get_or_create_tag(fields['tag'])
            color_id = tag.google_color_id

        jira_base_url = self.jira_client.base_url
        issue_url = f"{jira_base_url}/browse/{fields['key']}"

        due_date = datetime.strptime(fields['due_date'], '%Y-%m-%d')

        if synced_issue:
            # Update existing event
            title = self.tag_parser.format_title(
                fields['tag'], fields['summary'], fields['key']
            )
            gcal_client.update_event(
                calendar_id=user.google_calendar_id or 'primary',
                event_id=synced_issue.google_event_id,
                summary=title,
                due_date=due_date
            )
            action = 'updated'
        else:
            # Create new event
            event_id = gcal_client.create_event(
                calendar_id=user.google_calendar_id or 'primary',
                summary=fields['summary'],
                due_date=due_date,
                description=fields['description'],
                tag=fields['tag'],
                issue_key=fields['key'],
                issue_url=issue_url,
                color_id=color_id,
                status=fields['status'],
                priority=fields['priority'],
                assignee=fields['assignee_name']
            )

            synced_issue = SyncedIssue.objects.create(
                jira_issue_key=fields['key'],
                jira_issue_id=fields['id'],
                google_event_id=event_id,
                user=user
            )
            action = 'created'

        # Update checksums
        synced_issue.field_checksums = self.change_detector.build_checksums(fields)
        synced_issue.last_jira_update = timezone.now()
        synced_issue.save()

        # Log history
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action=action,
            source='jira',
            field_changes=fields
        )

        return synced_issue

    def sync_gcal_to_jira(
        self,
        synced_issue: SyncedIssue,
        gcal_event: Dict[str, Any]
    ) -> None:
        """Sync Google Calendar changes back to Jira."""
        fields = self.extract_gcal_fields(gcal_event)

        # Build update payload
        jira_updates = {}

        if fields['summary']:
            jira_updates['summary'] = fields['summary']

        if fields['due_date']:
            jira_updates['duedate'] = fields['due_date']

        if fields['tag']:
            jira_updates['labels'] = [fields['tag']]

        if jira_updates:
            self.jira_client.update_issue(synced_issue.jira_issue_key, jira_updates)

        # Update checksums
        synced_issue.field_checksums = self.change_detector.build_checksums(fields)
        synced_issue.last_gcal_update = timezone.now()
        synced_issue.save()

        # Log history
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action='updated',
            source='gcal',
            field_changes=fields
        )

    def handle_deletion(
        self,
        synced_issue: SyncedIssue,
        source: str
    ) -> None:
        """Handle deletion from either system."""
        user = synced_issue.user

        if source == 'jira':
            # Jira issue deleted -> delete calendar event
            credentials = json.loads(user.get_google_credentials())
            gcal_client = self.gcal_client_factory(credentials)
            try:
                gcal_client.delete_event(
                    calendar_id=user.google_calendar_id or 'primary',
                    event_id=synced_issue.google_event_id
                )
            except Exception:
                pass  # Event may already be deleted

        elif source == 'gcal':
            # Calendar event deleted -> delete Jira issue
            try:
                self.jira_client.delete_issue(synced_issue.jira_issue_key)
            except Exception:
                pass  # Issue may already be deleted

        # Log and archive
        SyncHistory.objects.create(
            synced_issue=synced_issue,
            action='deleted',
            source=source,
            field_changes={'deleted_from': source}
        )

        synced_issue.sync_enabled = False
        synced_issue.save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sync_engine.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/sync_engine.py tests/test_sync_engine.py
git commit -m "feat: add sync engine for bidirectional synchronization"
```

---

## Task 13: Celery Tasks

**Files:**
- Create: `sync/tasks.py`
- Create: `tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tasks.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from sync.tasks import run_sync, get_jira_client, get_sync_engine

class TestTasks:
    @patch('sync.tasks.JiraClient')
    def test_get_jira_client(self, mock_jira_client):
        with patch.dict('os.environ', {
            'JIRA_BASE_URL': 'https://test.atlassian.net',
            'JIRA_EMAIL': 'test@test.com',
            'JIRA_API_TOKEN': 'token123'
        }):
            client = get_jira_client()

        mock_jira_client.assert_called_once()

    @patch('sync.tasks.get_jira_client')
    @patch('sync.tasks.SyncConfig.objects')
    @patch('sync.tasks.JiraUser.objects')
    def test_run_sync_no_configs(self, mock_users, mock_configs, mock_get_client):
        mock_configs.filter.return_value = []

        result = run_sync()

        assert 'No active sync configs' in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tasks.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'sync.tasks'"

- [ ] **Step 3: Write minimal implementation**

```python
# sync/tasks.py
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import JiraUser, SyncedIssue, SyncConfig, Tag
from .jira_client import JiraClient
from .gcal_client import GoogleCalendarClient
from .sync_engine import SyncEngine
from .change_detector import ChangeDetector
from .conflict_handler import ConflictHandler

logger = logging.getLogger(__name__)

def get_jira_client() -> JiraClient:
    """Create Jira client from settings."""
    return JiraClient(
        base_url=settings.JIRA_BASE_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN
    )

def get_gcal_client(credentials: Dict[str, Any]) -> GoogleCalendarClient:
    """Create Google Calendar client from credentials."""
    return GoogleCalendarClient(credentials)

def get_sync_engine() -> SyncEngine:
    """Create sync engine with configured clients."""
    return SyncEngine(
        jira_client=get_jira_client(),
        gcal_client_factory=get_gcal_client
    )

@shared_task(bind=True, max_retries=3)
def run_sync(self) -> str:
    """Main sync task that runs every 30 seconds."""
    try:
        configs = list(SyncConfig.objects.filter(is_active=True))

        if not configs:
            return "No active sync configs"

        engine = get_sync_engine()
        jira_client = get_jira_client()
        change_detector = ChangeDetector()

        sync_stats = {
            'jira_to_gcal': 0,
            'gcal_to_jira': 0,
            'conflicts': 0,
            'errors': 0
        }

        # Process each config
        for config in configs:
            try:
                # Get updated Jira issues
                issues = jira_client.get_issues_updated_since(
                    projects=[config.jira_project_key],
                    issue_types=config.issue_types,
                    since_minutes=1,
                    additional_jql=config.additional_jql or ''
                )

                for issue in issues:
                    try:
                        process_jira_issue(engine, issue, sync_stats)
                    except Exception as e:
                        logger.error(f"Error processing Jira issue {issue.get('key')}: {e}")
                        sync_stats['errors'] += 1

            except Exception as e:
                logger.error(f"Error processing config {config.jira_project_key}: {e}")
                sync_stats['errors'] += 1

        # Process Google Calendar changes for all active users
        users = JiraUser.objects.filter(is_active=True).exclude(google_credentials_encrypted='')

        for user in users:
            try:
                process_gcal_changes(engine, user, change_detector, sync_stats)
            except Exception as e:
                logger.error(f"Error processing Google Calendar for {user.email}: {e}")
                sync_stats['errors'] += 1

        return f"Sync complete: {sync_stats}"

    except Exception as e:
        logger.exception(f"Sync task failed: {e}")
        raise self.retry(exc=e, countdown=10)

def process_jira_issue(
    engine: SyncEngine,
    issue: Dict[str, Any],
    stats: Dict[str, int]
) -> None:
    """Process a single Jira issue for sync."""
    fields = engine.extract_jira_fields(issue)

    if not fields['assignee_email']:
        return  # No assignee, skip

    # Find user
    try:
        user = JiraUser.objects.get(email=fields['assignee_email'], is_active=True)
    except JiraUser.DoesNotExist:
        return  # User not set up for sync

    if not user.google_credentials_encrypted:
        return  # No Google credentials

    # Check for existing sync
    synced_issue = SyncedIssue.objects.filter(
        jira_issue_key=fields['key'],
        user=user,
        sync_enabled=True
    ).first()

    engine.sync_jira_to_gcal(user, issue, synced_issue)
    stats['jira_to_gcal'] += 1

def process_gcal_changes(
    engine: SyncEngine,
    user: JiraUser,
    change_detector: ChangeDetector,
    stats: Dict[str, int]
) -> None:
    """Process Google Calendar changes for a user."""
    credentials = json.loads(user.get_google_credentials())
    gcal_client = GoogleCalendarClient(credentials)

    # Get recently updated events
    since = timezone.now() - timedelta(minutes=1)
    events = gcal_client.get_events_updated_since(
        calendar_id=user.google_calendar_id or 'primary',
        since=since
    )

    for event in events:
        try:
            fields = engine.extract_gcal_fields(event)
            issue_key = fields.get('issue_key')

            if not issue_key:
                continue  # Not a synced event

            synced_issue = SyncedIssue.objects.filter(
                jira_issue_key=issue_key,
                user=user,
                sync_enabled=True
            ).first()

            if not synced_issue:
                continue

            # Detect changes
            gcal_changes = change_detector.detect_changes(
                synced_issue.field_checksums,
                fields
            )

            if not gcal_changes:
                continue

            # Check for Jira changes too (conflict detection)
            jira_issue = engine.jira_client.get_issue(issue_key)
            jira_fields = engine.extract_jira_fields(jira_issue)
            jira_changes = change_detector.detect_changes(
                synced_issue.field_checksums,
                jira_fields
            )

            # Find conflicts
            conflicts = change_detector.find_conflicts(jira_changes, gcal_changes)

            if conflicts:
                # Create conflict in Jira
                for field_name, conflict_data in conflicts.items():
                    engine.conflict_handler.create_conflict_in_jira(
                        issue_key=issue_key,
                        field_name=field_name,
                        jira_value=conflict_data['jira_value'],
                        gcal_value=conflict_data['gcal_value']
                    )
                stats['conflicts'] += len(conflicts)
            else:
                # No conflict, sync from Google Calendar to Jira
                engine.sync_gcal_to_jira(synced_issue, event)
                stats['gcal_to_jira'] += 1

        except Exception as e:
            logger.error(f"Error processing calendar event {event.get('id')}: {e}")
            stats['errors'] += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tasks.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add sync/tasks.py tests/test_tasks.py
git commit -m "feat: add Celery sync tasks for 30-second polling"
```

---

## Task 14: Final Integration and Testing

**Files:**
- Modify: `config/settings.py` (fix app names)
- Create: `.env` (from template)

- [ ] **Step 1: Verify all imports work**

Create a simple integration test:

```python
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
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Create .env from template**

```bash
cp .env.example .env
# Edit .env with actual values
```

- [ ] **Step 4: Build and test Docker**

Run:
```bash
docker-compose build
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

Expected: All services start, migrations run successfully

- [ ] **Step 5: Verify admin access**

Open: http://localhost:8000/admin/
Expected: Django admin login page, can log in with superuser credentials

- [ ] **Step 6: Final commit**

```bash
git add tests/test_integration.py
git commit -m "feat: complete Jira-Google Calendar sync service"
```

---

## Task 15: Create Default Tags

**Files:**
- Create: `sync/management/__init__.py`
- Create: `sync/management/commands/__init__.py`
- Create: `sync/management/commands/setup_default_tags.py`

- [ ] **Step 1: Create management command directories**

```bash
mkdir -p sync/management/commands
touch sync/management/__init__.py
touch sync/management/commands/__init__.py
```

- [ ] **Step 2: Create setup command**

```python
# sync/management/commands/setup_default_tags.py
from django.core.management.base import BaseCommand
from sync.models import Tag

class Command(BaseCommand):
    help = 'Create default tags for calendar sync'

    DEFAULT_TAGS = [
        {'name': 'PM', 'color_hex': '#4CAF50', 'google_color_id': 10},
        {'name': 'Repair', 'color_hex': '#F44336', 'google_color_id': 11},
        {'name': 'Installation', 'color_hex': '#2196F3', 'google_color_id': 9},
        {'name': 'Inspection', 'color_hex': '#FFEB3B', 'google_color_id': 5},
    ]

    def handle(self, *args, **options):
        for tag_data in self.DEFAULT_TAGS:
            tag, created = Tag.objects.get_or_create(
                name=tag_data['name'],
                defaults={
                    'color_hex': tag_data['color_hex'],
                    'google_color_id': tag_data['google_color_id']
                }
            )
            status = 'Created' if created else 'Already exists'
            self.stdout.write(f"{status}: {tag.name}")

        self.stdout.write(self.style.SUCCESS('Default tags setup complete'))
```

- [ ] **Step 3: Run setup command**

Run: `docker-compose exec web python manage.py setup_default_tags`
Expected: Tags created or already exist message

- [ ] **Step 4: Commit**

```bash
git add sync/management/
git commit -m "feat: add management command for default tags"
```

---

## Summary

This implementation plan covers:

1. **Project Setup** - Docker, dependencies, Django config
2. **Security** - Fernet encryption for OAuth tokens
3. **Data Models** - All 6 models as per spec
4. **Admin** - Django admin for IT management
5. **Tag Parser** - [TAG] prefix handling
6. **Jira Client** - Full REST API wrapper
7. **Google Calendar Client** - Calendar API wrapper
8. **Change Detector** - Field-level checksums
9. **Conflict Handler** - Jira-native resolution
10. **OAuth Flow** - User self-service setup
11. **Sync Engine** - Bidirectional sync logic
12. **Celery Tasks** - 30-second polling
13. **Integration Testing** - Full system verification
14. **Default Tags** - PM, Repair, etc.

Total: ~15 tasks, TDD approach throughout, frequent commits.
