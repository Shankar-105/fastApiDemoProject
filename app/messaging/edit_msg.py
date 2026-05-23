from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app import models
from fastapi import APIRouter,Depends
from datetime import datetime
from app.schemas import CanEditResponse
from app import oauth2,db,config
from app.utils.socket_manager import manager
from app.services import redis_service
from datetime import datetime,timedelta,timezone
from app.utils.time_formatting import format_timestamp
import json
import logging


logger = logging.getLogger("app")

router=APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

@router.get("/messages/{msg_id}/can-edit", response_model=CanEditResponse)
async def can_edit(msg_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
    logger.debug("Checking edit window", extra={"extra_info": {"message_id": msg_id, "user_id": currentUser.id}})
    result = await db.execute(
        select(models.Message).where(
            models.Message.id == msg_id,
            models.Message.sender_id == currentUser.id
        )
    )
    message = result.scalars().first()
    if not message:
        return CanEditResponse(can_edit=False, message="Message not found")
    
    curr_time=datetime.now(timezone.utc)
    time_diff = curr_time - message.created_at
    if time_diff > timedelta(minutes=config.settings.max_edit_time):
        return CanEditResponse(can_edit=False)
    return CanEditResponse(can_edit=True)
    
async def edit_message(db:AsyncSession,message_id:int,new_content:str,sender_id:int,recv_id:int):
    logger.info("Editing message", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": recv_id}})
    result = await db.execute(
        select(models.Message).where(
            models.Message.id == message_id,
            models.Message.sender_id == sender_id,
        )
    )
    message = result.scalars().first()

    if not message:
        logger.warning("Edit message failed: message not found", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id}})
        return None

    curr_time = datetime.now(timezone.utc)
    created_at = message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    if curr_time - created_at > timedelta(minutes=config.settings.max_edit_time):
        payload = {
            "type": "edit_message_denied",
            "message_id": message_id,
            "reason": "edit_window_expired",
        }
        await manager.send_personal_message(payload, sender_id)
        logger.warning("Edit message denied: edit window expired", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id}})
        return

    if message.content.strip() == new_content:
        payload = {
            "type": "edit_message",
            "new_content": message.content,
            "message_id": message_id,
            "is_edited": False if not message.is_edited else True,
        }
        await manager.send_json_to_user(payload, recv_id)
        await manager.send_personal_message(payload, sender_id)
        logger.debug("Edit message skipped because content was unchanged", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id}})
        return

    edit_window_floor = curr_time - timedelta(minutes=config.settings.max_edit_time)
    update_result = await db.execute(
        update(models.Message)
        .where(
            models.Message.id == message_id,
            models.Message.sender_id == sender_id,
            models.Message.created_at >= edit_window_floor,
            models.Message.is_deleted_for_everyone == False,
        )
        .values(
            content=new_content,
            is_edited=True,
            is_read=False,
            read_at=None,
            edited_at=datetime.utcnow(),
        )
    )

    if not update_result.rowcount:
        payload = {
            "type": "edit_message_denied",
            "message_id": message_id,
            "reason": "edit_window_expired",
        }
        await manager.send_personal_message(payload, sender_id)
        logger.warning("Edit message denied after update check", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id}})
        return

    await db.commit()
    await db.refresh(message)
    logger.info("Message edited successfully", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": recv_id}})

    payload = {
        "type": "edit_message",
        "new_content": new_content,
        "message_id": message_id,
        "is_edited": True,
        "receiver_id": recv_id,
    }
    sender_payload = dict(payload)
    sender_payload["receiver_id"] = sender_id

    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("Edit message published to Redis", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": recv_id}})
    except Exception as e:
        logger.warning("Failed to publish edited message to Redis", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": recv_id, "error": str(e)}})
        try:
            if recv_id in manager.active_connections:
                await manager.send_json_to_user(payload, recv_id)
                await db.execute(
                    update(models.Message)
                    .where(models.Message.id == message.id, models.Message.is_read == False)
                    .values(is_read=True, read_at=datetime.utcnow())
                )
                await db.commit()
            else:
                logger.debug("Receiver offline; edited message stays in DB", extra={"extra_info": {"message_id": message_id, "receiver_id": recv_id}})
        except Exception as e2:
            logger.warning("Local send failed for edited message", extra={"extra_info": {"message_id": message_id, "error": str(e2)}})

        try:
            await manager.send_personal_message(sender_payload, sender_id)
        except Exception:
            pass
