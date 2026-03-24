import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('jira_gcal_sync')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Schedule sync task every 10 seconds
app.conf.beat_schedule = {
    'sync-jira-gcal-every-10-seconds': {
        'task': 'sync.tasks.run_sync',
        'schedule': 10.0,
    },
}
