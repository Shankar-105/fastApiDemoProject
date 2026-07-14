from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query,HTTPException
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.utils.socket_manager import manager
from app.services import redis_service
import json,asyncio
from datetime import datetime
import structlog


logger = structlog.get_logger(__name__)

router=APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

# same as the message_reaction but here the shares are
# stored in the SharedPosts table so we query that insted of
# the messages table
@router.post("/shares/{share_id}/delete")
async def deleteForMe(
    share_id: int,
    db: AsyncSession=Depends(db.getDb),
    me: models.User = Depends(oauth2.getCurrentUser),
):
    """Soft-delete a shared post for the current user only.

    Creates a DeletedSharedPost record to hide the share from the caller's
    history without affecting the chat partner's view. Operates analogously
    to delete_msg.deleteForMe but against the SharedPosts table. Called from
    the share context menu "Delete for me" action.
    """
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
    """Mark a shared post as deleted for everyone and notify both users.

    Atomically sets is_deleted_for_everyone = True on the SharedPost row with
    a concurrency-safe WHERE guard. Publishes a "share_deleted" event to Redis
    pub/sub, falling back to local WebSocket delivery. Called from the
    WebSocket dispatch loop when type == "delete_share_for_everyone".
    """
    logger.info("deleting_shared_post_everyone", share_id=share_id, sender_id=sender_id, receiver_id=receiver_id)
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
        logger.warning("delete_share_failed_not_found", share_id=share_id, sender_id=sender_id)
        return

    await db.commit()
    # Notify BOTH users instantly
    payload = {
        "type":"share_deleted",
        "share_id": share_id,
        "is_deleted_for_everyone":True,
        "receiver_id": receiver_id
    }
    logger.debug("delete_share_payload_prepared", share_id=share_id, sender_id=sender_id, receiver_id=receiver_id)
    
    sender_payload = dict(payload)
    sender_payload["receiver_id"] = sender_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("share_deletion_published_redis", share_id=share_id, sender_id=sender_id, receiver_id=receiver_id)
    except Exception as e:
        logger.warning("share_deletion_publish_redis_failed", share_id=share_id, sender_id=sender_id, receiver_id=receiver_id, error=str(e))
        try:
            await manager.send_json_to_user(payload, receiver_id)
        except Exception:
            manager.disconnect(receiver_id)
        try:
            await manager.send_personal_message(sender_payload, sender_id)
        except Exception:
            pass
