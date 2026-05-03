# Task package for Celery autodiscovery.
from app.tasks import email_tasks  # noqa: F401
from app.tasks import notification_tasks  # noqa: F401
from app.tasks import otp_cleanup_task  # noqa: F401
