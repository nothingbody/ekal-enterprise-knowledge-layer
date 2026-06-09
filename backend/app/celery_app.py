"""
Celery application configuration.
Uses Redis as both broker and result backend.
"""
from celery import Celery
from app.config import settings

celery = Celery(
    "rag_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=600,
    task_time_limit=900,
)

celery.conf.beat_schedule = {
    "cleanup-old-logs": {
        "task": "app.tasks.maintenance_tasks.cleanup_old_logs_task",
        "schedule": 86400,  # every 24 hours
        "args": (90,),      # retain 90 days
    },
    "cleanup-old-conversations": {
        "task": "app.tasks.maintenance_tasks.cleanup_old_conversations_task",
        "schedule": 604800,  # every 7 days
        "args": (180,),      # retain 180 days
    },
    "knowledge-health-check": {
        "task": "app.tasks.compilation_tasks.scheduled_health_checks_task",
        "schedule": 3600,  # every hour, checks which KBs are due
    },
}

celery.autodiscover_tasks(["app.tasks"])
