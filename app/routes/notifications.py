from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import app.schemas as sch
from app import models, db, oauth2
from app.services import notification_service as ns
from app.services.redis_service import get_cache, set_cache, delete_cache_pattern

router = APIRouter(
    prefix="/users/me/notifications",
    tags=["Notifications"]
)

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
    """Return paginated notifications for the authenticated user, newest first."""
    # Check Redis cache
    cache_key = f"notifications:{current_user.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
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
    """Return the unread notification count - used for the badge number in the UI."""
    cache_key = f"notif:unread:{current_user.id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    count = await ns.get_unread_count(db_session, current_user.id)
    result = sch.UnreadCountResponse(count=count)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=20)
    return result


@router.patch(
    "/read",
    status_code=status.HTTP_200_OK,
    response_model=sch.SuccessResponse,
)
async def mark_all_notifications_read(
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    """Mark every unread notification for the current user as read."""
    await ns.mark_all_read(db_session, current_user.id)
    # Invalidate notification caches for this user
    await delete_cache_pattern(f"notifications:{current_user.id}:*")
    await delete_cache_pattern(f"notif:unread:{current_user.id}")
    return sch.SuccessResponse(message="All notifications marked as read")

