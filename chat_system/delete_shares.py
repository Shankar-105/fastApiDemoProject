from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query,HTTPException
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.utils.socket_manager import manager
from app.services import redis_service
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
        return

    await db.commit()
    # Notify BOTH users instantly
    payload = {
        "type":"share_deleted",
        "share_id": share_id,
        "is_deleted_for_everyone":True,
        "receiver_id": receiver_id
    }
    print(f"Sender ID {sender_id} Receiver ID {receiver_id}")
    
    sender_payload = dict(payload)
    sender_payload["receiver_id"] = sender_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        print("Share deletion published to Redis for cross-process delivery (receiver+sender)")
    except Exception as e:
        print(f"Failed to publish to Redis: {e}")
        try:
            await manager.send_json_to_user(payload, receiver_id)
        except Exception:
            manager.disconnect(receiver_id)
        try:
            await manager.send_personal_message(sender_payload, sender_id)
        except Exception:
            pass
