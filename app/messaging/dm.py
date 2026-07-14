from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.utils.socket_manager import manager
from app.utils.time_formatting import format_timestamp
from app.services import redis_service
from datetime import datetime
import json
import structlog


logger = structlog.get_logger(__name__)
               
async def messageUser(
    payload:schemas.MessageSchema,
    user_id:int,
    db:AsyncSession
):
    """Save and deliver a direct message between two users.

    Persists the Message record, then publishes both a sender copy and a
    receiver copy to Redis pub/sub on "chat:messages" for cross-worker
    delivery. If Redis is unavailable, falls back to local WebSocket sends.
    When the receiver is online the message is also marked as read immediately.
    Called from the WebSocket dispatch loop in chat.py for the default
    (non-reply, non-reaction) message type.
    """    
    logger.info("creating_direct_message", sender_id=user_id, receiver_id=payload.to)
    msg = models.Message(
        content=payload.content,
        sender_id=user_id,
        receiver_id=payload.to,
        media_type=payload.media_type,
        media_url=payload.media_url,
    )
    db.add(msg)
    await db.commit()
    # No refresh needed - expire_on_commit=False keeps object attributes
    logger.info("direct_message_saved", sender_id=user_id, receiver_id=payload.to)

    reply_payload = {
        "id": msg.id,
        "content": msg.content,
        "media_url": msg.media_url,
        "media_type": msg.media_type,
        "sender_id": user_id,
        "receiver_id": payload.to,
        "type": "message",
        "timestamp": format_timestamp(msg.created_at),
        "is_reply": False,
        "is_reply_to_share": False,
    }

    # Publish to Redis for cross-process delivery. Also publish a copy intended
    # for the sender so both users get delivered via Redis regardless of
    # which worker they're connected to. If Redis is unavailable, fall back
    # to local sends.
    sender_payload = dict(reply_payload)
    sender_payload["receiver_id"] = user_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(reply_payload))
        logger.info("direct_message_published_redis", message_id=msg.id, sender_id=user_id, receiver_id=payload.to)
    except Exception as e:
        logger.warning("direct_message_publish_redis_failed", message_id=msg.id, sender_id=user_id, receiver_id=payload.to, error=str(e))
        # Best-effort local delivery when Redis is down
        try:
            receiver_id = msg.receiver_id
            if receiver_id in manager.active_connections:
                await manager.send_json_to_user(reply_payload, payload.to)
                await db.execute(
                    update(models.Message)
                    .where(models.Message.id == msg.id, models.Message.is_read == False)
                    .values(is_read=True, read_at=datetime.utcnow())
                )
                await db.commit()
            else:
                logger.debug("receiver_offline_dm_saved", message_id=msg.id, receiver_id=payload.to)
        except Exception as e2:
            logger.warning("direct_message_local_send_failed", message_id=msg.id, error=str(e2))

        try:
            await manager.send_personal_message(sender_payload, user_id)
        except Exception:
            pass
