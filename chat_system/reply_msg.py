from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.my_utils.socket_manager import manager
from app.services import redis_service
from datetime import datetime
from app.my_utils.time_formatting import format_timestamp
import json


async def reply_msg(
    payload:schemas.ReplyMessageSchema,
    user_id:int,
    db:AsyncSession
):    
        # avioiding users from replying to a deleted message
        subq=(
        select(models.DeletedMessage.message_id)
        .where(models.DeletedMessage.user_id == user_id)
        .scalar_subquery()
        )
        result = await db.execute(
            select(models.Message).where(
                models.Message.id == payload.reply_msg_id,
                models.Message.is_deleted_for_everyone == False,
                ~models.Message.id.in_(subq)
            ).with_for_update()
        )
        original_msg = result.scalars().first()
        if not original_msg:
             print("cannot reply to a deleted message")
             return
        msg = models.Message(
                        content=payload.content,
                        sender_id=user_id,
                        receiver_id=payload.to,
                        is_reply_msg=True,
                        media_type=payload.media_type,
                        media_url=payload.media_url
                    )
        db.add(msg)
        await db.flush()
        await db.refresh(msg)
        reply_link = models.MessageReplies(
            reply_id=msg.id,
            original_id=payload.reply_msg_id
        )
        db.add(reply_link)
        await db.commit()
        print("added to db")
        # Check if receiver is in active_connections
        receiver_id = msg.receiver_id
        if receiver_id in manager.active_connections:
            try:
                reply_message_payload={
                "type": "message",
                "id": msg.id,
                "content": msg.content,
                "sender_id": user_id,
                "receiver_id": payload.to,
                "timestamp": format_timestamp(msg.created_at),
                "is_reply": True,
                "is_reply_to_share": False,
                "media_url":msg.media_url,
                "media_type":msg.media_type,
                # original message
                "reply_to": {
                    "msg_id": original_msg.id,
                    "content":  original_msg.content,
                    "sender_name": original_msg.sender.username,
                    "media_url":original_msg.media_url,
                    "media_type":original_msg.media_type,
                }
        }
                # Publish to Redis for cross-process delivery; publish both
                # receiver and sender copies so both users are delivered.
                # If Redis is unavailable, fall back to local sends.
                sender_payload = dict(reply_message_payload)
                sender_payload["receiver_id"] = user_id
                redis_published = False
                try:
                    await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
                    await redis_service.redis_client.publish("chat:messages", json.dumps(reply_message_payload))
                    redis_published = True
                    print("Reply message published to Redis for cross-process delivery (receiver+sender)")
                except Exception as e:
                    print(f"Failed to publish to Redis: {e}")
                    # fallback to local sends for receiver
                    try:
                        await manager.send_json_to_user(reply_message_payload, receiver_id)
                        await db.execute(
                            update(models.Message)
                            .where(models.Message.id == msg.id, models.Message.is_read == False)
                            .values(is_read=True, read_at=datetime.utcnow())
                        )
                        await db.commit()
                    except Exception as e2:
                        print(f"Local send failed: {e2}")
                    try:
                        await manager.send_personal_message(sender_payload, user_id)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Send failed: {e}")
                manager.disconnect(receiver_id)
        else:
            print("Receiver offline — message saved in DB")
        # Send response back to sender (local response is redundant when Redis worked,
        # but keep it as a fallback for very small latency-sensitive flows)
        payload_to_user={
            "type": "message",
                "id": msg.id,
                "content": msg.content,
                "sender_id": user_id,
            "receiver_id": payload.to,
                "timestamp":format_timestamp(msg.created_at),
                "is_reply": True,
                "is_reply_to_share": False,
                "media_url":msg.media_url,
                "media_type":msg.media_type,
                "reply_to": {
                    "msg_id": original_msg.id,
                    "content":  original_msg.content,
                    "sender_name": original_msg.sender.username,
                    "media_url":original_msg.media_url,
                    "media_type":original_msg.media_type,
                }
        }
        # Only send local response to sender if Redis publish failed
        if not locals().get('redis_published', False):
            try:
                await manager.send_personal_message(payload_to_user, user_id)
                print("Response sent to sender (local fallback)")
            except Exception:
                pass
