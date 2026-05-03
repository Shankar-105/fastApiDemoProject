from fastapi import File, UploadFile, APIRouter, Depends, Form
from uuid import uuid4
from app import oauth2
from app.services.blob_service import upload_blob
from app.services import redis_service
from app.my_utils.socket_manager import manager
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.my_utils.time_formatting import format_timestamp
import json

router = APIRouter()

@router.post("/media/send")
async def send_media(
    file: UploadFile = File(...),
    to: int = Form(...),
    current_user = Depends(oauth2.getCurrentUser),
    db: AsyncSession = Depends(getDb),
):
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
        print("Media message published to Redis for cross-process delivery (sender+receiver)")
    except Exception as e:
        print(f"Failed to publish media to Redis: {e}")
        # fallback local sends
        try:
            if to in manager.active_connections:
                await manager.send_json_to_user(payload, to)
            else:
                print("Receiver offline — media message saved in DB")
        except Exception:
            manager.disconnect(to)
        try:
            await manager.send_personal_message(sender_payload, current_user.id)
        except Exception:
            pass

    return {"media_url": media_url, "type": media_type, "message_id": msg.id}
