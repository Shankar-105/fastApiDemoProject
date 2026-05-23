from fastapi import APIRouter,WebSocket, WebSocketDisconnect,Depends,Query,HTTPException
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.utils.socket_manager import manager
from app.services import redis_service
import json,asyncio
from datetime import datetime
import logging


logger = logging.getLogger("app")

router=APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

# a http route to handle the delete for me click from the user
# its not a web socket route like the delete for everyone message because
# when a user clicks on the delete for me button its enough to show the
# user that the message is deleted so doesn't envolve the receiver so we dont
# have a need here to use the websockets just let the frontend do its ui work
@router.post("/messages/{msg_id}")
async def deleteForMe(
    msg_id: int,
    db: AsyncSession=Depends(db.getDb),
    me: models.User = Depends(oauth2.getCurrentUser),
):
    result = await db.execute(
        select(models.Message).where(models.Message.id==msg_id)
    )
    message = result.scalars().first()
    if not message:
        return
    insert_stmt = (
        pg_insert(models.DeletedMessage)
        .values(user_id=me.id, message_id=msg_id)
        .on_conflict_do_nothing(
            index_elements=[models.DeletedMessage.user_id, models.DeletedMessage.message_id]
        )
    )
    insert_result = await db.execute(insert_stmt)
    await db.commit()
    detail = "Already deleted for you" if insert_result.rowcount == 0 else "Deleted for you"
    return {"message_id": msg_id, "detail": detail}
 
 # delete for everyone method
 # here we mark the message as deleted for everyone is true
 # and instanly pass that as deleted via websokcets
async def delete_for_everyone(
    db:AsyncSession,
    message_id:int,
    sender_id: int,
    receiver_id: int,
    ):
    logger.info("Deleting message for everyone", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": receiver_id}})
    # Atomic transition prevents duplicate broadcasts during retries/concurrency.
    update_result = await db.execute(
        update(models.Message)
        .where(
            models.Message.id == message_id,
            models.Message.sender_id == sender_id,
            models.Message.is_deleted_for_everyone == False,
        )
        .values(is_deleted_for_everyone=True)
    )
    if not update_result.rowcount:
        logger.warning("Delete-for-everyone failed: message not found", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id}})
        return

    await db.commit()
    # Notify BOTH users instantly
    payload = {
        "type":"delete_message",
        "message_id": message_id,
        "is_deleted_for_everyone":True,
        "receiver_id": receiver_id
    }
    logger.debug("Prepared delete-for-everyone payload", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": receiver_id}})
    
    sender_payload = dict(payload)
    sender_payload["receiver_id"] = sender_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("Delete message published to Redis", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": receiver_id}})
    except Exception as e:
        logger.warning("Failed to publish delete message to Redis", extra={"extra_info": {"message_id": message_id, "sender_id": sender_id, "receiver_id": receiver_id, "error": str(e)}})
        # Fallback to local sends
        try:
            await manager.send_json_to_user(payload, receiver_id)
        except Exception:
            manager.disconnect(receiver_id)
        try:
            await manager.send_personal_message(sender_payload, sender_id)
        except Exception:
            pass
    else:
        # Also send locally so tests and local feedback receive immediate delivery
        try:
            await manager.send_json_to_user(payload, receiver_id)
        except Exception:
            manager.disconnect(receiver_id)
        try:
            await manager.send_personal_message(sender_payload, sender_id)
        except Exception:
            pass
