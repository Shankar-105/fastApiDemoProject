from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.db import AsyncSessionLocal
from app.models import Notification, NotificationType
from app.services.redis_service import delete_cache_pattern
from app.my_utils.socket_manager import manager

# -- Patchable session factory --
# Mirrors exactly what redis_service.py does with redis_client.
# In production this is AsyncSessionLocal (production DB).
# In tests conftest.py replaces it with TestingAsyncSessionLocal so
# background tasks write to the test DB, not the production DB.
_session_factory = AsyncSessionLocal


# -- Human-readable notification text builders --
# Lambda per type: given the actor's username, produce the display string.

_NOTIFICATION_TEXT = {
    NotificationType.like:    lambda actor: f"{actor} liked your post",
    NotificationType.comment: lambda actor: f"{actor} commented on your post",
    NotificationType.follow:  lambda actor: f"{actor} started following you",
}


async def create_notification(
    actor_id: int,
    owner_id: int,
    notif_type: NotificationType,
    actor_username: str,
    entity_id: int | None = None,
    entity_type: str | None = None,
) -> None:
    # Belt-and-suspenders self-notification guard.
    # The caller already checks this, but if this function is ever called from
    # anywhere else we never want a user to get their own notification.
    if actor_id == owner_id:
        return

    text = _NOTIFICATION_TEXT[notif_type](actor_username)

    # -- Step A: Persist to DB --
    # We open a FRESH session here. The route's session is already closed by
    # the time BackgroundTasks run (FastAPI closes it when the response is sent).
    # We use _session_factory (not AsyncSessionLocal directly) so tests can
    # patch this module to use the test DB instead of production.
    async with _session_factory() as db:
        notif = Notification(
            owner_id=owner_id,
            actor_id=actor_id,
            type=notif_type,
            entity_id=entity_id,
            entity_type=entity_type,
            text=text,
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)     # <- needed to get the auto-assigned id + created_at

        # Invalidate notification caches for the recipient
        await delete_cache_pattern(f"notifications:{owner_id}:*")
        await delete_cache_pattern(f"notif:unread:{owner_id}")

        payload = {
            "type":         "notification",
            "id":           notif.id,
            "actor_id":     actor_id,
            "actor_username": actor_username,
            "notif_type":   notif_type.value,
            "entity_id":    entity_id,
            "entity_type":  entity_type,
            "text":         text,
            "is_read":      False,
            "created_at":   notif.created_at.isoformat() if notif.created_at else None,
        }
        
        await manager.send_personal_message(payload, owner_id)


# -- REST helper functions --
# These are called by the notification routes added in step 7.
# Defined here (not inside the routes) to keep the service layer clean.

async def get_notifications(
    db: AsyncSession,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[Notification]:
    """Return paginated notifications for a user, newest first."""
    result = await db.execute(
        select(Notification)
        .where(Notification.owner_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    """Return the count of unread notifications - used for the badge number."""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.owner_id == user_id, Notification.is_read == False)    # noqa: E712
    )
    return result.scalar() or 0


async def mark_all_read(db: AsyncSession, user_id: int) -> None:
    """Bulk-mark every unread notification for a user as read."""
    await db.execute(
        update(Notification)
        .where(Notification.owner_id == user_id, Notification.is_read == False)    # noqa: E712
        .values(is_read=True)
    )
    await db.commit()

