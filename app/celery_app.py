from celery import Celery
from celery.schedules import crontab, schedule
from kombu import Exchange, Queue
from app.config import settings
from app.utils.logging import setup_logging

# Initialize logging for Celery
setup_logging()


celery_app = Celery(
    "social_media_api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_default_retry_delay=60,
    task_default_max_retries=3,
    result_expires=86400,
    task_acks_on_failure_or_timeout=False,
    worker_disable_rate_limits=False,
    task_soft_time_limit=600,
    task_time_limit=900,
)

celery_app.conf.task_routes = {
    "app.tasks.*": {"queue": "celery", "routing_key": "celery"},
}

# Declare dead-letter exchange queue so RabbitMQ will persist failed tasks
dead_letter_exchange = Exchange("dead_letter_exchange", type="direct", durable=True)
dead_letter_queue = Queue(
    "dead_letter_queue", exchange=dead_letter_exchange, routing_key="dead_letter", durable=True
)

celery_queue = Queue(
    "celery",
    Exchange("celery", type="direct"),
    routing_key="celery",
    queue_arguments={
        "x-dead-letter-exchange": "dead_letter_exchange",
        "x-dead-letter-routing-key": "dead_letter",
    },
)

celery_app.conf.task_queues = (celery_queue, dead_letter_queue)

celery_app.conf.beat_schedule = {
    "cleanup-expired-otps": {
        "task": "app.tasks.otp_cleanup_task.cleanup_expired_otps",
        "schedule": crontab(minute=0),
        "options": {"queue": "celery"},
    },
    "reconcile-denormalized-counters": {
        "task": "app.tasks.reconciliation_task.reconcile_denormalized_counters_task",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "celery"},
    },
    "flush-post-views": {
        "task": "app.tasks.post_view_flush_task.flush_post_views",
        # Run every 5 minutes
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "celery"},
    },
}

celery_app.autodiscover_tasks(["app.tasks"])
