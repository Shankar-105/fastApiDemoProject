from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.utils.socket_manager import manager
from app.services import redis_service
from datetime import datetime
from app.utils.time_formatting import format_timestamp
import json
import structlog


logger = structlog.get_logger(__name__)


async def reply_msg(
    payload:schemas.ReplyMessageSchema,
    user_id:int,
    db:AsyncSession
):
    """Send a reply to a specific message in a conversation.

    Validates the original message still exists and hasn't been deleted by the
    user (checks DeletedMessage table). Creates the reply Message and a
    MessageReplies link row. Publishes to Redis pub/sub for cross-worker
    delivery (with local WebSocket fallback). The response payload includes
    a "reply_to" block with the original message's content and sender name.
    Called from the WebSocket dispatch loop when type == "reply_message".
    """    
    logger.info("creating_reply_message", reply_msg_id=payload.reply_msg_id, sender_id=user_id, receiver_id=payload.to)

    subq = (
        select(models.DeletedMessage.message_id)
        .where(models.DeletedMessage.user_id == user_id)
        .scalar_subquery()
    )
    result = await db.execute(
        select(models.Message).where(
            models.Message.id == payload.reply_msg_id,
            models.Message.is_deleted_for_everyone == False,
            ~models.Message.id.in_(subq),
        ).with_for_update()
    )
    original_msg = result.scalars().first()
    if not original_msg:
        logger.warning("reply_to_deleted_message_denied", reply_msg_id=payload.reply_msg_id, sender_id=user_id)
        return

    msg = models.Message(
        content=payload.content,
        sender_id=user_id,
        receiver_id=payload.to,
        is_reply_msg=True,
        media_type=payload.media_type,
        media_url=payload.media_url,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    reply_link = models.MessageReplies(
        reply_id=msg.id,
        original_id=payload.reply_msg_id,
    )
    db.add(reply_link)
    await db.commit()
    logger.info("reply_message_saved", message_id=msg.id, reply_msg_id=payload.reply_msg_id, sender_id=user_id, receiver_id=payload.to)

    receiver_id = msg.receiver_id
    redis_published = False
    if receiver_id in manager.active_connections:
        try:
            reply_message_payload = {
                "type": "message",
                "id": msg.id,
                "content": msg.content,
                "sender_id": user_id,
                "receiver_id": payload.to,
                "timestamp": format_timestamp(msg.created_at),
                "is_reply": True,
                "is_reply_to_share": False,
                "media_url": msg.media_url,
                "media_type": msg.media_type,
                "reply_to": {
                    "msg_id": original_msg.id,
                    "content": original_msg.content,
                    "sender_name": original_msg.sender.username,
                    "media_url": original_msg.media_url,
                    "media_type": original_msg.media_type,
                },
            }
            sender_payload = dict(reply_message_payload)
            sender_payload["receiver_id"] = user_id

            try:
                await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
                await redis_service.redis_client.publish("chat:messages", json.dumps(reply_message_payload))
                redis_published = True
                logger.info("reply_message_published_redis", message_id=msg.id, sender_id=user_id, receiver_id=payload.to)
            except Exception as e:
                logger.warning("reply_message_publish_redis_failed", message_id=msg.id, sender_id=user_id, receiver_id=payload.to, error=str(e))
                try:
                    await manager.send_json_to_user(reply_message_payload, receiver_id)
                    await db.execute(
                        update(models.Message)
                        .where(models.Message.id == msg.id, models.Message.is_read == False)
                        .values(is_read=True, read_at=datetime.utcnow())
                    )
                    await db.commit()
                except Exception as e2:
                    logger.warning("Local send failed for reply message", extra={"extra_info": {"message_id": msg.id, "error": str(e2)}})
                try:
                    await manager.send_personal_message(sender_payload, user_id)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Send failed for reply message", extra={"extra_info": {"message_id": msg.id, "error": str(e)}})
            manager.disconnect(receiver_id)
    else:
        logger.debug("Receiver offline; reply message remains in DB", extra={"extra_info": {"message_id": msg.id, "receiver_id": payload.to}})

    payload_to_user = {
        "type": "message",
        "id": msg.id,
        "content": msg.content,
        "sender_id": user_id,
        "receiver_id": payload.to,
        "timestamp": format_timestamp(msg.created_at),
        "is_reply": True,
        "is_reply_to_share": False,
        "media_url": msg.media_url,
        "media_type": msg.media_type,
        "reply_to": {
            "msg_id": original_msg.id,
            "content": original_msg.content,
            "sender_name": original_msg.sender.username,
            "media_url": original_msg.media_url,
            "media_type": original_msg.media_type,
        },
    }

    if not redis_published:
        try:
            await manager.send_personal_message(payload_to_user, user_id)
            logger.debug("Response sent to sender via local fallback", extra={"extra_info": {"message_id": msg.id, "sender_id": user_id}})
        except Exception:
            pass
