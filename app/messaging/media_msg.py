from fastapi import File, UploadFile, APIRouter, Depends, Form
from uuid import uuid4
from app import oauth2
from app.services.blob_service import upload_blob
from app.services import redis_service
from app.utils.socket_manager import manager
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.utils.time_formatting import format_timestamp
import json
import logging


logger = logging.getLogger("app")

router = APIRouter(
    prefix="/messaging",
    tags=["Messaging"]
)

@router.post("/messages/media")
async def send_media(
    file: UploadFile = File(...),
    to: int = Form(...),
    current_user = Depends(oauth2.getCurrentUser),
    db: AsyncSession = Depends(getDb),
):
    logger.info("Sending media message", extra={"extra_info": {"sender_id": current_user.id, "receiver_id": to}})
    # 'video', 'audio', 'image'
    media_type = file.content_type.split("/")[0]
    file_extension = file.filename.split(".")[-1]
    blob_name = f"{media_type}s/{uuid4()}.{file_extension}"
    content_bytes = await file.read()
    media_url = await upload_blob("chat-media", blob_name, content_bytes, file.content_type)

    # Persist message to DB and publish via Redis (publish-first, fallback local)
    msg = models.Message(
        content="",
        sender_id=current_user.id,
        receiver_id=to,
        media_type=media_type,
        media_url=media_url,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    payload = {
        "id": msg.id,
        "content": msg.content,
        "media_url": msg.media_url,
        "media_type": msg.media_type,
        "sender_id": current_user.id,
        "receiver_id": to,
        "type": "message",
        "timestamp": format_timestamp(msg.created_at),
        "is_reply": False,
        "is_reply_to_share": False,
    }

    sender_payload = dict(payload)
    sender_payload["receiver_id"] = current_user.id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("Media message published to Redis", extra={"extra_info": {"message_id": msg.id, "sender_id": current_user.id, "receiver_id": to}})
    except Exception as e:
        logger.warning("Failed to publish media message to Redis", extra={"extra_info": {"message_id": msg.id, "sender_id": current_user.id, "receiver_id": to, "error": str(e)}})
        # fallback local sends
        try:
            if to in manager.active_connections:
                await manager.send_json_to_user(payload, to)
            else:
                logger.debug("Receiver offline; media message remains in DB", extra={"extra_info": {"message_id": msg.id, "receiver_id": to}})
        except Exception:
            manager.disconnect(to)
        try:
            await manager.send_personal_message(sender_payload, current_user.id)
        except Exception:
            pass

    return {"media_url": media_url, "type": media_type, "message_id": msg.id}
