"""
Celery application configuration for HomeScout background tasks.
Uses Redis as message broker.
"""
import os
from dotenv import load_dotenv
from celery import Celery
from celery.schedules import crontab

# Load environment variables from .env file
load_dotenv()

# Redis URL for message broker
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "homescout",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.scrape_tasks",
        "app.tasks.maintenance_tasks",
        "app.tasks.dispatcher",
        "app.tasks.alert_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time

    # Result backend settings
    result_expires=86400,  # 24 hours

    # Task time limits
    task_soft_time_limit=1800,  # 30 minutes soft limit (default)
    task_time_limit=3600,  # 1 hour hard limit (default)

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Rate limiting
    worker_disable_rate_limits=False,
)

# Beat schedule — 3 orchestrator tasks only
celery_app.conf.beat_schedule = {
    # Dispatcher: check which markets need scraping
    "dispatch-scrapes": {
        "task": "app.tasks.dispatcher.dispatch_scrapes",
        "schedule": crontab(minute=0),  # Every hour at :00
    },

    # Decay confidence scores and trigger verification
    "decay-and-verify": {
        "task": "app.tasks.maintenance_tasks.decay_and_verify",
        "schedule": crontab(minute=30),  # Every hour at :30
    },

    # Daily maintenance at 3 AM UTC
    "cleanup-maintenance": {
        "task": "app.tasks.maintenance_tasks.cleanup_maintenance",
        "schedule": crontab(hour=3, minute=0),
    },

    # Daily email alerts for Pro users at 8 AM ET (13:00 UTC)
    "send-daily-alerts": {
        "task": "app.tasks.alert_tasks.send_daily_alerts",
        "schedule": crontab(hour=13, minute=0),
    },
}

# Optional: Configure task routes for different queues
celery_app.conf.task_routes = {
    "app.tasks.scrape_tasks.*": {"queue": "scraping"},
    "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
}


def get_celery_app() -> Celery:
    """Get the Celery application instance."""
    return celery_app
