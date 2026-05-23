from fastapi import APIRouter, HTTPException ,Depends
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.utils.socket_manager import manager
from app.services import redis_service
from datetime import datetime
from typing import List
import json
import structlog


logger = structlog.get_logger(__name__)
router=APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)


@router.get("/messages/{msg_id}/reactions",response_model=List[schemas.ReactedUsers])
async def msg_reactions(
    msg_id:int,
    db: AsyncSession = Depends(db.getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser)
):
    logger.debug("fetching_message_reactions", message_id=msg_id, user_id=currentUser.id)
    result = await db.execute(
        select(models.Message).where(models.Message.id == msg_id)
    )
    msg = result.scalars().first()
    if not msg:
        raise HTTPException(404, "Message not found")

    if msg.sender_id != currentUser.id and msg.receiver_id != currentUser.id:
        return

    reactions_result = await db.execute(
        select(models.MessageReaction)
        .options(selectinload(models.MessageReaction.user))
        .where(models.MessageReaction.message_id == msg_id)
    )
    reactions = reactions_result.scalars().all()
    return [
        {
            "user_id": r.user.id,
            "username": r.user.username,
            "profile_pic": r.user.profile_picture,
            "reaction": r.reaction,
        }
        for r in reactions
    ]


async def react(
    reaction:schemas.ReactionPayload,
    user_id:int,
    db: AsyncSession
): 
    logger.info("handling_message_reaction", message_id=reaction.message_id, user_id=user_id, reaction=reaction.reaction)
    result = await db.execute(
        select(models.Message).where(models.Message.id == reaction.message_id)
    )
    the_msg = result.scalars().first()
    if not the_msg:
        return {
            "status": "Message not found"
        }
    elgibile = [the_msg.sender_id, the_msg.receiver_id]
    if user_id not in elgibile:
        logger.warning("message_reaction_unauthorized", message_id=reaction.message_id, user_id=user_id)
        return {
            "status": "Unknown User"
        }
    existing_result = await db.execute(
        select(models.MessageReaction).where(
            models.MessageReaction.message_id == reaction.message_id,
            models.MessageReaction.user_id == user_id
        )
    )
    msg = existing_result.scalars().first()
    # if there's no such record in MessageReaction Table
    # then this is the first new reaction by the user with id as user_id 
    # so create a MessageReaction object and add it to that tble
    isNewRecord = False
    if not msg:
        isNewRecord=True
        new_reaction=models.MessageReaction(message_id=reaction.message_id,user_id=user_id,reaction=reaction.reaction)
        db.add(new_reaction)
    # the msg reaction already exists in that tbale but the
    # user has again sent the same reaction well then remove it 
    elif msg and msg.reaction == reaction.reaction:
        isNewRecord=False
        await db.delete(msg)
    # msg exists and the new reation isnt the old one
    # well then he sent a brand new reaciton just change it
    else:
        isNewRecord=True
        msg.reaction=reaction.reaction
    # any changes commit thehm off
    await db.commit()
    await db.refresh(the_msg)
    
    # payload
    payload = {
        "type": "reaction",
        "message_id": the_msg.id,
        "reaction": reaction.reaction if isNewRecord else None,
        "reaction_count": the_msg.reaction_cnt,
        "reacted_by": user_id,
        "receiver_id": the_msg.receiver_id
    }
    sender_payload = dict(payload)
    sender_payload["receiver_id"] = the_msg.sender_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("Reaction published to Redis", extra={"extra_info": {"message_id": the_msg.id, "user_id": user_id}})
    except Exception as e:
        logger.warning("Failed to publish message reaction to Redis", extra={"extra_info": {"message_id": the_msg.id, "user_id": user_id, "error": str(e)}})
        # Fallback local sends
        try:
            await manager.send_personal_message(sender_payload, the_msg.sender_id)
        except Exception:
            pass
        try:
            await manager.send_json_to_user(payload, the_msg.receiver_id)
        except Exception:
            manager.disconnect(the_msg.receiver_id)
