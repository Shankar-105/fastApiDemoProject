from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import app.schemas as sch
from app import models, db, oauth2
from app.services import notification_service as ns
from app.services.redis_service import get_cache, set_cache, delete_cache_pattern
from app.services.idempotency_service import get_idempotency_key, idempotent
import structlog

router = APIRouter(
    prefix="/users/me/notifications",
    tags=["Notifications"]
)

logger = structlog.get_logger(__name__)

@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=sch.NotificationListResponse,
)

async def get_my_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    """Return paginated notifications for the current user.

    Cached per ``notifications:{user.id}:{offset}:{limit}`` for 20
    seconds.  Includes the ``unread_count`` and ``total`` alongside the
    notification list so the UI can show badges in one call.
    Delegates to ``notification_service`` for domain logic.
    """
    logger.debug("fetching_notifications", user_id=current_user.id, limit=limit, offset=offset)
    cache_key = f"notifications:{current_user.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("notifications_cache_hit", user_id=current_user.id)
        return cached

    notifications = await ns.get_notifications(db_session, current_user.id, limit, offset)
    unread_count = await ns.get_unread_count(db_session, current_user.id)

    total_result = await db_session.execute(
        select(func.count())
        .select_from(models.Notification)
        .where(models.Notification.owner_id == current_user.id)
    )
    total = total_result.scalar() or 0

    result = sch.NotificationListResponse(
        notifications=notifications,
        unread_count=unread_count,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=20)
    logger.info("notifications_retrieved_db", user_id=current_user.id, count=len(notifications))
    return result


@router.get(
    "/unread-count",
    status_code=status.HTTP_200_OK,
    response_model=sch.UnreadCountResponse,
)

async def get_unread_notification_count(
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    """Return the count of unread notifications for the current user.

    Cached under ``notif:unread:{user.id}`` for 20 seconds.  This is a
    lightweight endpoint the client polls periodically (or on app
    foreground) to update the notification badge.
    """
    logger.debug("fetching_unread_notif_count", user_id=current_user.id)
    cache_key = f"notif:unread:{current_user.id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("unread_notif_count_cache_hit", user_id=current_user.id)
        return cached

    count = await ns.get_unread_count(db_session, current_user.id)
    result = sch.UnreadCountResponse(count=count)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=20)
    logger.info("unread_notif_count_retrieved", user_id=current_user.id, count=count)
    return result


@router.patch(
    "/read",
    status_code=status.HTTP_200_OK,
    response_model=sch.SuccessResponse,
)
@idempotent(endpoint_identifier="mark_notifications_read")
async def mark_all_notifications_read(
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """Mark every notification for the current user as read.

    Idempotent — calling this multiple times is safe.  Purges all
    notification caches for the user (both list and unread-count) so
    the badge updates to zero immediately.
    """
    logger.info("mark_all_notifications_read_attempt", user_id=current_user.id)
    await ns.mark_all_read(db_session, current_user.id)
    await delete_cache_pattern(f"notifications:{current_user.id}:*")
    await delete_cache_pattern(f"notif:unread:{current_user.id}")
    logger.info("mark_all_notifications_read_success", user_id=current_user.id)
    return sch.SuccessResponse(message="All notifications marked as read")

