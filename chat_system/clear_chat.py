from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2,config,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_,and_,select,insert,literal
from typing import List

router=APIRouter(
    prefix="/v1/messaging",
    tags=['Messaging']
)

@router.delete("/conversations/{friend_id}")
async def clear_chat(friend_id:int,db:AsyncSession =Depends(db.getDb),current_user:models.User=Depends(oauth2.getCurrentUser)):
    
    # messages already deleted by me
    deleted_subq = (
        select(models.DeletedMessage.message_id)
        .where(models.DeletedMessage.user_id == current_user.id)
        .scalar_subquery()
    )

    # find all VISIBLE messages in this chat
    visible_messages = (
        select(models.Message.id)  # we only need message_id
        .where(
            models.Message.is_deleted_for_everyone == False,
            or_(
                and_(models.Message.sender_id == current_user.id, models.Message.receiver_id == friend_id),
                and_(models.Message.sender_id == friend_id, models.Message.receiver_id == current_user.id, models.Message.is_read == True)
            ),
            ~models.Message.id.in_(deleted_subq)
        )
    )
    # Insert all those message_ids into DeletedMessage table for this user
    await db.execute(
    insert(models.DeletedMessage).from_select(
        ["user_id","message_id"],
        visible_messages.with_only_columns(
            literal(current_user.id),models.Message.id
        )
    )
)
    await db.commit()
    return {"detail": "Chat cleared successfully"}