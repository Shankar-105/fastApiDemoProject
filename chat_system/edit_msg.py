from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app import models
from fastapi import APIRouter,Depends
from datetime import datetime
from app.schemas import CanEditResponse
from app import oauth2,db,config
from app.my_utils.socket_manager import manager
from datetime import datetime,timedelta,timezone
from app.my_utils.time_formatting import format_timestamp

router=APIRouter(tags=['can_edit'])

@router.get("/msg/{msg_id}/can_edit", response_model=CanEditResponse)
async def can_edit(msg_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
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
    result = await db.execute(
        select(models.Message).where(
            models.Message.id == message_id,
            models.Message.sender_id == sender_id
        )
    )
    message = result.scalars().first()
    
    if not message:
        return None
    curr_time = datetime.now(timezone.utc)
    created_at = message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if curr_time - created_at > timedelta(minutes=config.settings.max_edit_time):
        payload = {
            "type": "edit_message_denied",
            "message_id": message_id,
            "reason": "edit_window_expired"
        }
        await manager.send_personal_message(payload, sender_id)
        return
    # Don't update if content is same
    if message.content.strip() == new_content:
        # No change
        payload = {
        "type":"edit_message",
        "new_content":message.content,
        "message_id": message_id,
        "is_edited":False if not message.is_edited else True
    }
        await manager.send_json_to_user(payload,recv_id)
        await manager.send_personal_message(payload,sender_id)
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
            "reason": "edit_window_expired"
        }
        await manager.send_personal_message(payload, sender_id)
        return

    await db.commit()
    await db.refresh(message)
    print(message.is_read)
    payload = {
        "type":"edit_message",
        "new_content":new_content,
        "message_id": message_id,
        "is_edited":True
    }
    if recv_id in manager.active_connections:
                    try:
                        await manager.send_json_to_user(payload, 
                            recv_id
                        )
                        print("Message sent via WebSocket")
                        message.is_read = True
                        message.read_at=datetime.utcnow()
                        await db.commit()
                        print(f"Message {message.id} marked as READ")
                    except Exception as e:
                        print(f"Send failed: {e}")
                        manager.disconnect(recv_id)
    else:
            print("Receiver offline — message saved in DB")
    await manager.send_personal_message(payload,sender_id)