from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query,HTTPException
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.my_utils.socket_manager import manager
import json,asyncio
from datetime import datetime

router=APIRouter(tags=['delete share'])

# same as the message_reaction but here the shares are
# stored in the SharedPosts table so we query that insted of
# the messages table
@router.post("/delete-share/for-me/{share_id}")
async def deleteForMe(
    share_id: int,
    db: AsyncSession=Depends(db.getDb),
    me: models.User = Depends(oauth2.getCurrentUser),
):
    result = await db.execute(
        select(models.SharedPost).where(models.SharedPost.id==share_id)
    )
    share = result.scalars().first()
    if not share:
        return
    deleted_share=models.DeletedSharedPost(
        user_id=me.id,
        shared_post_id=share_id
    )
    db.add(deleted_share)
    await db.commit()
    return {"share_id": share_id, "detail": "Deleted for you"}

async def delete_share_for_everyone(
    db:AsyncSession,
    share_id:int,
    sender_id: int,
    receiver_id: int,
    ):
    print(f"Message ID {share_id} Sender ID {sender_id} Recv ID {receiver_id}")
    update_result = await db.execute(
        update(models.SharedPost)
        .where(
            models.SharedPost.id == share_id,
            models.SharedPost.from_user_id == sender_id,
            models.SharedPost.is_deleted_for_everyone == False,
        )
        .values(is_deleted_for_everyone=True)
    )
    if not update_result.rowcount:
        print("Message Not Found")
        return {
            "status": "not_found",
            "share_id": share_id,
        }

    await db.commit()
    # Notify BOTH users instantly
    payload = {
        "type":"share_deleted",
        "share_id": share_id,
        "is_deleted_for_everyone":True
    }
    print(f"Sender ID {sender_id} Receiver ID {receiver_id}")
    await manager.send_json_to_user(payload,receiver_id)
    await manager.send_personal_message(payload,sender_id)
    return {
        "status": "ok",
        "result": payload
    }