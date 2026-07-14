import json
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.db import AsyncSessionLocal
from app.models import Notification, NotificationType
from app.services import redis_service
from app.services.redis_service import delete_cache_pattern
from app.utils.socket_manager import manager


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


_NOTIFICATION_CHANNEL = "notifications:messages"


logger = structlog.get_logger(__name__)


async def create_notification(
    actor_id: int,
    owner_id: int,
    notif_type: NotificationType,
    actor_username: str,
    entity_id: int | None = None,
    entity_type: str | None = None,
) -> None:
    """Persist a notification row and push it to the recipient in real-time.

    This is called from background tasks (not directly from routes) after
    a like, comment, or follow action completes.  The route's DB session is
    already closed when the task runs, so we open a fresh session via
    ``_session_factory``.

    We publish the notification to Redis pub/sub on the ``notifications:messages``
    channel.  The cross-worker listener in ``main.py`` picks it up and delivers
    it to the connected WebSocket of the recipient.  If Redis is unavailable
    we fall back to the local socket manager (single-worker mode).

    Self-notifications are silently dropped — we never notify a user of their
    own action, even though the callers already guard against this.
    """
    logger.info(
        "notification_creating",
        actor_id=actor_id,
        owner_id=owner_id,
        notif_type=notif_type.value,
        entity_id=entity_id,
        entity_type=entity_type,
    )
    # Belt-and-suspenders self-notification guard.
    # The caller already checks this, but if this function is ever called from
    # anywhere else we never want a user to get their own notification.
    if actor_id == owner_id:
        return

    text = _NOTIFICATION_TEXT[notif_type](actor_username)

    # -- Step A: Persist to DB --
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
        await db.refresh(notif)

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
            "receiver_id":  owner_id,
        }

        try:
            await redis_service.redis_client.publish(
                _NOTIFICATION_CHANNEL,
                json.dumps(payload),
            )
            logger.info(
                "notification_published_to_redis",
                notification_id=notif.id,
                owner_id=owner_id,
            )
        except Exception:
            # Redis is the cross-worker delivery path; fall back to the local
            # socket manager only if pub/sub is unavailable.
            logger.warning(
                "notification_publish_failed_falling_back",
                notification_id=notif.id,
                owner_id=owner_id,
            )
            await manager.send_personal_message(payload, owner_id)


async def get_notifications(
    db: AsyncSession,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[Notification]:
    """Return paginated notifications for a user, newest first.

    Called from GET /v1/users/me/notifications.  The route layer handles
    caching; this function always queries the DB.
    """
    logger.debug(
        "fetching_notifications",
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    result = await db.execute(
        select(Notification)
        .where(Notification.owner_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    """Return the count of unread notifications, used for the badge number.

    Called from GET /v1/users/me/notifications/unread-count.
    """
    logger.debug("Fetching unread notification count", extra={"extra_info": {"user_id": user_id}})
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.owner_id == user_id, Notification.is_read == False)    # noqa: E712
    )
    return result.scalar() or 0


async def mark_all_read(db: AsyncSession, user_id: int) -> None:
    """Bulk-mark every unread notification for a user as read.

    Called from PATCH /v1/users/me/notifications/read.
    After this the badge count will be zero on next refresh.
    """
    logger.info("Marking all notifications read", extra={"extra_info": {"user_id": user_id}})
    await db.execute(
        update(Notification)
        .where(Notification.owner_id == user_id, Notification.is_read == False)    # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
