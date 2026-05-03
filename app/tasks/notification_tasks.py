from app.celery_app import celery_app
from app.models import NotificationType


@celery_app.task(bind=True, max_retries=3)
def create_notification_task(
    self,
    actor_id: int,
    owner_id: int,
    notif_type: str,
    actor_username: str,
    entity_id: int | None = None,
    entity_type: str | None = None,
):
    try:
        import asyncio
        from app.services.notification_service import create_notification
        
        asyncio.run(
            create_notification(
                actor_id=actor_id,
                owner_id=owner_id,
                notif_type=NotificationType(notif_type),
                actor_username=actor_username,
                entity_id=entity_id,
                entity_type=entity_type,
            )
        )
    except Exception as exc:
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)
