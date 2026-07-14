from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2,config,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_,and_,select,insert,literal
from typing import List
import structlog


logger = structlog.get_logger(__name__)

router=APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

@router.delete("/conversations/{friend_id}")
async def clear_chat(friend_id:int,db:AsyncSession =Depends(db.getDb),current_user:models.User=Depends(oauth2.getCurrentUser)):
    """Soft-delete all visible messages in a conversation for the current user.

    Bulk-inserts entries into the DeletedMessage table for every message in the
    chat that isn't already deleted-for-everyone or previously hidden by this
    user. Only the caller's perspective is affected — the conversation partner
    still sees their copy. Idempotent: skipped messages are excluded via a
    NOT EXISTS subquery. Called from the "Clear Chat" UI action.
    """
    logger.info("clearing_chat", user_id=current_user.id, friend_id=friend_id)
    
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
    logger.info("chat_cleared_success", user_id=current_user.id, friend_id=friend_id)
    return {"detail": "Chat cleared successfully"}
