from fastapi import File, UploadFile, APIRouter, Depends, Form
from uuid import uuid4
from app import oauth2
from app.services.blob_service import upload_blob, validate_and_read_file, safe_extension
from app.services import redis_service
from app.utils.socket_manager import manager
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.utils.time_formatting import format_timestamp
import json
import structlog


logger = structlog.get_logger(__name__)

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
    logger.info("sending_media_message", sender_id=current_user.id, receiver_id=to)
    # 'video', 'audio', 'image'
    media_type = file.content_type.split("/")[0]
    file_extension = safe_extension(file.filename)
    blob_name = f"{media_type}s/{uuid4()}.{file_extension}" if file_extension else f"{media_type}s/{uuid4()}"
    content_bytes = await validate_and_read_file(file)
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
        logger.info("media_message_published_redis", message_id=msg.id, sender_id=current_user.id, receiver_id=to)
    except Exception as e:
        logger.warning("media_message_publish_redis_failed", message_id=msg.id, sender_id=current_user.id, receiver_id=to, error=str(e))
        # fallback local sends
        try:
            if to in manager.active_connections:
                await manager.send_json_to_user(payload, to)
            else:
                logger.debug("receiver_offline_media_saved", message_id=msg.id, receiver_id=to)
        except Exception:
            manager.disconnect(to)
        try:
            await manager.send_personal_message(sender_payload, current_user.id)
        except Exception:
            pass

    return {"media_url": media_url, "type": media_type, "message_id": msg.id}
