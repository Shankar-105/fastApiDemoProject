from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from app.utils.socket_manager import manager
from app.services import redis_service
from datetime import datetime
from app.utils.time_formatting import format_timestamp
import json
import structlog


logger = structlog.get_logger(__name__)
async def reply_share(
    payload:schemas.ReplyToShareSchema,
    user_id:int,
    db: AsyncSession
):
    """Send a reply to a shared post in a conversation.

    Validates the SharedPost exists, creates a reply Message with
    is_reply_to_share=True, and links it via SharedPostReplies. Loads the
    original Post content for context and publishes the full payload
    (with post preview, owner name, media URL) to Redis pub/sub, falling
    back to local WebSocket delivery. Called from the WebSocket dispatch
    loop when type == "reply_to_share".
    """
    logger.info("creating_reply_to_share_message", shared_post_id=payload.shared_post_id, sender_id=user_id, receiver_id=payload.to)
    # Optional: Validate that shared_post exists and belongs to this chat
    result = await db.execute(
        select(models.SharedPost).where(models.SharedPost.id == payload.shared_post_id)
    )
    shared_post = result.scalars().first()

    if not shared_post:
        logger.warning("reply_to_share_invalid_post", shared_post_id=payload.shared_post_id, sender_id=user_id)
        return

    # Create the reply message
    reply_msg = models.Message(
        content=payload.content,
        sender_id=user_id,
        receiver_id=payload.to,
        is_reply_msg=True,           # still a reply 
        is_reply_to_share=True,
        media_type=payload.media_type,
        media_url=payload.media_url       # this is reply to a shared post
    )
    db.add(reply_msg)
    await db.commit()
    # No refresh needed - expire_on_commit=False keeps object attributes

    # Link reply message -> shared post
    reply_link = models.SharedPostReplies(
        reply_msg_id=reply_msg.id,
        shared_post_id=payload.shared_post_id
    )
    db.add(reply_link)
    await db.commit()

    # Load original post details for context
    post_result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.user))
        .where(models.Post.id == shared_post.post_id)
    )
    original_post = post_result.scalars().first()

    reply_payload = {
        "type": "message",
        "id": reply_msg.id,
        "content": reply_msg.content,
        "sender_id": user_id,
        "receiver_id": payload.to,
        "timestamp": format_timestamp(reply_msg.created_at),
        "is_reply": True,
        "is_reply_to_share": True,
        "media_url":reply_msg.media_url,
        "media_type":reply_msg.media_type,
        "reply_to_share": {
            "shared_post_id": shared_post.id,
            "post_id": shared_post.post_id,
            "post_content": original_post.content[:100] + "..." if len(original_post.content) > 100 else original_post.content,
            "post_owner": original_post.user.username,
            "media_url": original_post.media_path  # if exists
        }
    }


    sender_payload = dict(reply_payload)
    sender_payload["receiver_id"] = user_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(reply_payload))
        logger.info("reply_to_share_published_redis", message_id=reply_msg.id, sender_id=user_id, receiver_id=payload.to)
    except Exception as e:
        logger.warning("reply_to_share_publish_redis_failed", message_id=reply_msg.id, sender_id=user_id, receiver_id=payload.to, error=str(e))
        # fallback local send
        try:
            if payload.to in manager.active_connections:
                await manager.send_json_to_user(reply_payload, payload.to)
                await db.execute(
                    update(models.Message)
                    .where(models.Message.id == reply_msg.id, models.Message.is_read == False)
                    .values(is_read=True, read_at=datetime.utcnow())
                )
                await db.commit()
        except Exception:
            manager.disconnect(payload.to)

        try:
            await manager.send_personal_message(sender_payload, user_id)
        except Exception:
            pass
