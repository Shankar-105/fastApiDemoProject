from fastapi import APIRouter, HTTPException ,Depends
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.my_utils.socket_manager import manager
from datetime import datetime
from typing import List
router=APIRouter(tags=['msg reactions'])


@router.get("/msgs/{msg_id}/msg_reaction_info",response_model=List[schemas.ReactedUsers])
async def msg_reactions(
    msg_id:int,
    db: AsyncSession = Depends(db.getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser)
):
  result = await db.execute(
      select(models.Message).where(models.Message.id == msg_id)
  )
  msg = result.scalars().first()
  if not msg:
        raise HTTPException(404, "Message not found")
    # veryyy Optional highly impossible
  if msg.sender_id != currentUser.id and msg.receiver_id != currentUser.id:
        return
  reactions_result = await db.execute(
      select(models.MessageReaction).where(models.MessageReaction.message_id == msg_id)
  )
  reactions = reactions_result.scalars().all()
  return [
        {
            "user_id": r.user.id,
            "username": r.user.username,
            "profile_pic": r.user.profile_picture,
            "reaction": r.reaction
        }
        for r in reactions
    ]


async def react(
    reaction:schemas.ReactionPayload,
    user_id:int,
    db: AsyncSession
): 
    result = await db.execute(
        select(models.Message).where(models.Message.id == reaction.message_id)
    )
    the_msg = result.scalars().first()
    elgibile=[the_msg.sender_id,the_msg.receiver_id]
    print(user_id,elgibile)
    if user_id not in elgibile:
        print("working")
        return {
            "status":"Unknown User"
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
        await db.execute(
            update(models.Message)
            .where(models.Message.id == reaction.message_id)
            .values(reaction_cnt=models.Message.reaction_cnt + 1)
        )
    # the msg reaction already exists in that tbale but the
    # user has again sent the same reaction well then remove it 
    elif msg and msg.reaction == reaction.reaction:
        isNewRecord=False
        await db.delete(msg)
        await db.execute(
            update(models.Message)
            .where(models.Message.id == reaction.message_id)
            .values(reaction_cnt=func.greatest(models.Message.reaction_cnt - 1, 0))
        )
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
        "reacted_by": user_id
    }
    # Send to BOTH sender and receiver
    await manager.send_personal_message(payload,the_msg.sender_id)
    await manager.send_json_to_user(payload,the_msg.receiver_id)
