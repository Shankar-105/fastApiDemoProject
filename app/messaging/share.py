# routes/share.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional
from app.db import getDb
from app.models import SharedPost, Post, User
from app.schemas import SharePostRequest, SharedPostDetailResponse
from app.oauth2 import getCurrentUser
from app.utils.socket_manager import manager  # your WebSocket ConnectionManager
from app.utils.time_formatting import format_timestamp
from app.services import redis_service
import json
import structlog


logger = structlog.get_logger(__name__)


router = APIRouter(
    prefix="/messaging",
    tags=["Messaging"]
)

@router.post("/share", response_model=SharedPostDetailResponse)
async def share_post(
    payload: SharePostRequest,
    db: AsyncSession = Depends(getDb),
    me: User = Depends(getCurrentUser),
):
    """Share a post with another user via DM.

    Validates the post exists and the receiver exists and isn't the sender.
    Creates a SharedPost record, sends a preview to the receiver's WebSocket
    (marking it read immediately if they're online), and publishes both
    sender and receiver copies to Redis pub/sub for cross-worker delivery
    (with local fallback). Called from the "Share" button on a post.
    """
    """
    1. Validate post exists
    2. Validate receiver exists & not self
    3. Save SharedPost record
    4. Push a **preview** to receiver via WebSocket (if online)
    5. Return the DB record (for sender UI)
    """
    post_result = await db.execute(select(Post).where(Post.id == payload.post_id))
    post: Post = post_result.scalars().first()
    if not post:
        logger.warning("share_post_not_found", post_id=payload.post_id, sender_id=me.id)
        raise HTTPException(status_code=404, detail="Post not found")
    receiver_result = await db.execute(select(User).where(User.id == payload.to_user_id))
    receiver: User = receiver_result.scalars().first()
    if not receiver:
        logger.warning("share_receiver_not_found", post_id=payload.post_id, sender_id=me.id, receiver_id=payload.to_user_id)
        raise HTTPException(status_code=404, detail="Receiver not found")
    if receiver.id == me.id:
        logger.warning("share_self_denied", post_id=payload.post_id, sender_id=me.id)
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    shared = SharedPost(
        post_id=payload.post_id,
        from_user_id=me.id,
        to_user_id=receiver.id,
        message=payload.message,
    )
    db.add(shared)
    await db.commit()
    await db.refresh(shared)

    preview = {
        "type": "shared_post",
        "shared_id": shared.id,
        "post_id": post.id,
        "sender_id": me.id,
        "receiver_id": receiver.id,
        "title": (post.title or "")[:60] + ("..." if post.title and len(post.title) > 60 else ""),
        "media_type": post.media_type,
        "media_url": post.media_path,
    }

    if receiver.id in manager.active_connections:
        try:
            await manager.send_json_to_user(preview, receiver.id)
            await db.execute(
                update(SharedPost)
                .where(SharedPost.id == shared.id, SharedPost.is_read == False)
                .values(is_read=True)
            )
            await db.commit()
        except Exception:
            pass  # Offline or error → stays unread

    # Publish to Redis for cross-process delivery (publish receiver + sender copies).
    sender_payload = dict(preview)
    sender_payload["receiver_id"] = me.id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(preview))
        logger.info("share_published_redis", shared_id=shared.id, sender_id=me.id, receiver_id=receiver.id)
    except Exception as e:
        logger.warning("share_publish_redis_failed", shared_id=shared.id, sender_id=me.id, receiver_id=receiver.id, error=str(e))
        try:
            await manager.send_json_to_user(preview, receiver.id)
        except Exception:
            manager.disconnect(receiver.id)
        try:
            await manager.send_personal_message(sender_payload, me.id)
        except Exception:
            pass

    return shared
