from app.my_utils.time_formatting import format_timestamp
from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2,config
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_,and_,select,case,func
from sqlalchemy.orm import selectinload
from typing import List
from sqlalchemy.exc import IntegrityError
from app.my_utils.socket_manager import manager

router = APIRouter(prefix="/chat", tags=["chat_history"])

@router.get("/history/{friend_id}")
async def get_chat_history(
    friend_id: int,
    db: AsyncSession = Depends(getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser),
):
    # CRITICAL: Hide undelivered messages from friend
    # firstly let us fetch out the 'delted for me' msgs by the current user
    subq=(
        select(models.DeletedMessage.message_id)
        .where(models.DeletedMessage.user_id == currentUser.id)
        .scalar_subquery()
    )
    # now let us use that subquery in NOT EXISTS and simply query off the final messages
    messages_result = await db.execute(
        select(models.Message)
        .options(
            selectinload(models.Message.reactions),
            selectinload(models.Message.replies_to).selectinload(models.MessageReplies.original_msg).selectinload(models.Message.sender),
            selectinload(models.Message.reply_to_shared_post).selectinload(models.SharedPost.post),
            selectinload(models.Message.reply_to_shared_post).selectinload(models.SharedPost.from_user),
        )
        .where(
            # 1. Not deleted for everyone
            models.Message.is_deleted_for_everyone == False,
            # 2. Is between these two users
            or_(
                and_(models.Message.sender_id == currentUser.id, models.Message.receiver_id == friend_id),
                and_(models.Message.sender_id == friend_id, models.Message.receiver_id == currentUser.id)
            ),
            # 3. Not deleted by THIS user (NOT EXISTS)
            ~models.Message.id.in_(subq)
        )
        .order_by(models.Message.created_at.desc())
    )
    messages = messages_result.scalars().all()
    # shared posts

    deleted_shared_subq = (
        select(models.DeletedSharedPost.shared_post_id)
        .where(models.DeletedSharedPost.user_id == currentUser.id)
        .scalar_subquery()
    )
    shared_result = await db.execute(
        select(models.SharedPost)
        .options(
            selectinload(models.SharedPost.post),
            selectinload(models.SharedPost.from_user),
            selectinload(models.SharedPost.reactions),
        )
        .where(
            models.SharedPost.is_deleted_for_everyone == False,
            or_(
                and_(models.SharedPost.from_user_id == currentUser.id, models.SharedPost.to_user_id == friend_id),
                and_(models.SharedPost.from_user_id == friend_id, models.SharedPost.to_user_id == currentUser.id)
            ),
            ~models.SharedPost.id.in_(deleted_shared_subq)
        ).order_by(models.SharedPost.created_at.desc())
    )
    shared_posts = shared_result.scalars().all()

    chat_history=[]
    for m in messages:
        base_msg = {
            "type":"message",
            "id": m.id,
            "content": m.content,
            "sender_id":m.sender_id,
            "receiver_id":m.receiver_id,
            "media_type":m.media_type if m.media_type != "false" else None,
            "media_url":f"{config.settings.base_url}/chat-media{m.media_url}" if m.media_type != "false" else None,
            "timestamp": format_timestamp(m.created_at),
            "is_edited": m.is_edited,
            "reaction_count": m.reaction_cnt,
            "reactions": m.reactions,
            "is_read": m.is_read
        }
        # check whether its a reply message or not
        if m.is_reply_msg:
            # if so then check if its just a reply to a messgage or a post
            if m.is_reply_to_share:
                shared_post=m.reply_to_shared_post
                if shared_post:
                    base_msg.update({
                        "is_reply":True,
                        "is_reply_to_share": True,
                        "reply_to": {
                            "share_id":shared_post.id,
                            "content":shared_post.post.media_path,
                            "sender_name":shared_post.from_user.username if shared_post.from_user else "Unknown"
                        }
                    })
            else:
                original_msg=m.replies_to.original_msg
                if original_msg:
                    base_msg.update({
                        "is_reply": True,
                        "reply_to": {
                            "msg_id": original_msg.id,
                            "media_type":m.media_type if original_msg.media_type != "false" else None,
                            "media_url":f"{config.settings.base_url}/chat-media{original_msg.media_url}" if original_msg.media_type != "false" else None,
                            "content": original_msg.content,
                            "sender_name": original_msg.sender.username if original_msg.sender else "Unknown"
                        }
                    })
        else:
            base_msg["is_reply"] = False
        chat_history.append(base_msg)

    for s in shared_posts:
        chat_history.append({
            "type": "shared_post",
            "shared_id": s.id,
            "post_id": s.post.id,
            "sender_id": s.from_user_id,
            "receiver_id":s.to_user_id,
            "title":(s.post.title or "")[:60],
            "media_type": s.post.media_type,
            "media_url": s.post.media_path,
            "sender_nickname": s.from_user.nickname,
            "message": s.message,
            "reactions": s.reactions,
            "sent_at": format_timestamp(s.created_at),
            "is_read": s.is_read
        })
    chat_history.sort(key=lambda x : x.get("timestamp") if "timestamp" in  x else x.get("sent_at"))
    return chat_history  # oldest first

@router.get("/recent-chats")
async def get_recent_chats(
    db: AsyncSession = Depends(getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser)
):
    other_user_id = case(
        (models.Message.sender_id == currentUser.id, models.Message.receiver_id),
        else_=models.Message.sender_id,
    ).label("other_user_id")
    ranked_messages = (
        select(
            models.Message.id.label("message_id"),
            other_user_id,
            func.row_number()
            .over(partition_by=other_user_id, order_by=models.Message.created_at.desc())
            .label("rn"),
        )
        .where(
            or_(
                models.Message.sender_id == currentUser.id,
                models.Message.receiver_id == currentUser.id
            ),
            models.Message.is_deleted_for_everyone == False
        )
        .subquery()
    )

    recent_result = await db.execute(
        select(models.Message, models.User)
        .join(ranked_messages, ranked_messages.c.message_id == models.Message.id)
        .join(models.User, models.User.id == ranked_messages.c.other_user_id)
        .where(ranked_messages.c.rn == 1)
        .order_by(models.Message.created_at.desc())
    )
    recent_rows = recent_result.all()

    if not recent_rows:
        return []

    # Construct response
    results = []
    for msg, user in recent_rows:
        results.append({
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "profile_pic": user.profile_picture,
            "online": manager.is_online(user.id),
            "last_seen_at": None if manager.is_online(user.id) else (user.last_seen_at or manager.get_last_seen(user.id)),
            "last_message": {
                "content": msg.content,
                "timestamp": format_timestamp(msg.created_at),
                "is_read": msg.is_read,
                "is_me": msg.sender_id == currentUser.id,
                "media_type": msg.media_type
            }
        })

    return results
