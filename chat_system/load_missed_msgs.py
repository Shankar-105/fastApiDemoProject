from fastapi import Depends
from app import schemas, models, oauth2,db,config
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from app.my_utils.socket_manager import manager
from datetime import datetime
from app.my_utils.time_formatting import format_timestamp
from app.models import Notification

async def load_missed_content(
    user_id: int,
    db: AsyncSession=Depends(db.getDb)
):
        claimed_read_at = datetime.utcnow()
        missed_result = await db.execute(
            select(models.Message).where(
                models.Message.is_deleted_for_everyone==False,
                models.Message.receiver_id == user_id,
                models.Message.is_read == False
            ).order_by(models.Message.created_at.asc()).with_for_update(skip_locked=True)
            .options(selectinload(models.Message.reactions))  # Explicitly load reactions
        )
        missed_messages = missed_result.scalars().all()
        message_ids = [m.id for m in missed_messages]

        if message_ids:
            await db.execute(
                update(models.Message)
                .where(
                    models.Message.id.in_(message_ids),
                    models.Message.is_read == False
                )
                .values(is_read=True, read_at=claimed_read_at)
            )
            await db.commit()
            read_message_ids = set(message_ids)
        else:
            read_message_ids = set()

        missed_shares_result = await db.execute(
            select(models.SharedPost).where(
                models.SharedPost.to_user_id == user_id,
                models.SharedPost.is_read == False,
                models.SharedPost.is_deleted_for_everyone == False
            ).order_by(models.SharedPost.created_at.asc()).with_for_update(skip_locked=True)
        )
        missed_shares = missed_shares_result.scalars().all()
        share_ids = [s.id for s in missed_shares]
        
        if share_ids:
            await db.execute(
                update(models.SharedPost)
                .where(
                    models.SharedPost.id.in_(share_ids),
                    models.SharedPost.is_read == False
                )
                .values(is_read=True)
            )
            await db.commit()
            read_share_ids = set(share_ids)
        else:
            read_share_ids = set()

        missed_content=[]
        for m in missed_messages:
            base_msg = {
                "type": "message",
                "id": m.id,
                "content": m.content,
                "sender_id": m.sender_id,
                "receiver_id": m.receiver_id,
                "media_type":m.media_type if m.media_type != "false" else None,
                "media_url":f"{config.settings.base_url}/chat-media{m.media_url}" if m.media_type != "false" else None,
                "timestamp": format_timestamp(m.created_at),
                "is_edited": m.is_edited,
                "reaction_count": m.reaction_cnt,
                "reactions": m.reactions,
                "is_read": m.id in read_message_ids
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
                                "content": original_msg.content,
                                "media_type":m.media_type if original_msg.media_type != "false" else None,
                                "media_url":f"{config.settings.base_url}/chat-media{original_msg.media_url}" if original_msg.media_type != "false" else None,
                                "sender_name": original_msg.sender.username if original_msg.sender else "Unknown"
                            }
                        })
            else:
                base_msg["is_reply"] = False
            missed_content.append(base_msg)

        for s in missed_shares:
            missed_content.append({
                "type": "shared_post",
                "shared_id": s.id,
                "post_id": s.post.id,
                "sender_id": s.from_user_id,
                "receiver_id":s.to_user_id,
                "title": (s.post.title or "")[:60],
                "media_type": s.post.media_type,
                "media_url": s.post.media_path,
                "sender_nickname": s.from_user.nickname,
                "caption_message": s.message,
                "reactions": s.reactions,
                "sent_at": format_timestamp(s.created_at),
                "is_read": s.id in read_share_ids
            })
        # On every WebSocket connect we also push any notifications the user
        # missed while they were offline.
        # The actor relationship is eager-loaded (lazy="selectin" on the model),
        # so n.actor.username is available without an extra query.
        missed_notifs_result = await db.execute(
            select(Notification)
            .where(
                Notification.owner_id == user_id,
                Notification.is_read == False,
            )
            .order_by(Notification.created_at.asc())
        )
        missed_notifs = missed_notifs_result.scalars().all()

        for n in missed_notifs:
            missed_content.append({
                "type":           "notification",
                "id":             n.id,
                "notif_type":     n.type.value,          # "like" | "comment" | "follow"
                "actor_id":       n.actor_id,
                "actor_username": n.actor.username if n.actor else None,
                "text":           n.text,
                "entity_id":      n.entity_id,
                "entity_type":    n.entity_type,
                "timestamp":      format_timestamp(n.created_at),   # matches msgs sort key
                "is_read":        n.is_read,
            })

        missed_content.sort(key=lambda x : x.get("timestamp") if "timestamp" in  x else x.get("sent_at"))
        return missed_content