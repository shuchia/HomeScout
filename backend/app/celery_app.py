"""
Celery application configuration for HomeScout background tasks.
Uses Redis as message broker.
"""
import os
from celery import Celery
from celery.schedules import crontab

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
    task_soft_time_limit=1800,  # 30 minutes soft limit
    task_time_limit=3600,  # 1 hour hard limit

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Rate limiting
    worker_disable_rate_limits=False,
)

# Beat schedule for Bryn Mawr MVP
celery_app.conf.beat_schedule = {
    # Daily scrape at 6 AM EST (11 AM UTC)
    "scrape-bryn-mawr-daily": {
        "task": "app.tasks.scrape_tasks.scrape_source",
        "schedule": crontab(hour=11, minute=0),
        "args": ("apartments_com",),
        "kwargs": {
            "cities": ["Bryn Mawr"],
            "state": "PA",
            "max_listings_per_city": 200,
        },
    },

    # Cleanup stale after 3 days
    "cleanup-stale-listings": {
        "task": "app.tasks.maintenance_tasks.cleanup_stale_listings",
        "schedule": crontab(hour=12, minute=0),
        "kwargs": {"days_old": 3},
    },

    # Reset rate limits daily
    "reset-daily-rate-limits": {
        "task": "app.tasks.maintenance_tasks.reset_rate_limits",
        "schedule": crontab(hour=0, minute=0),
        "kwargs": {"period": "day"},
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
