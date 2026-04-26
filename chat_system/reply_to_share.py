from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.my_utils.socket_manager import manager
from datetime import datetime
from app.my_utils.time_formatting import format_timestamp
async def reply_share(
    payload:schemas.ReplyToShareSchema,
    user_id:int,
    db: AsyncSession
):
    # Optional: Validate that shared_post exists and belongs to this chat
    result = await db.execute(
        select(models.SharedPost).where(models.SharedPost.id == payload.shared_post_id)
    )
    shared_post = result.scalars().first()

    if not shared_post:
        print("Invalid or inaccessible shared post")
        return

    # Create the reply message
    reply_msg = models.Message(
        content=payload.content,
        sender_id=user_id,
        receiver_id=payload.to,
        is_reply_msg=True,           # still a reply 
        is_reply_to_share=True,
        media_type=payload.media_type,
        media_url=payload.media_url       # this is reply to a shared post
    )
    db.add(reply_msg)
    await db.commit()
    await db.refresh(reply_msg)

    # Link reply message -> shared post
    reply_link = models.SharedPostReplies(
        reply_msg_id=reply_msg.id,
        shared_post_id=payload.shared_post_id
    )
    db.add(reply_link)
    await db.commit()

    # Load original post details for context
    post_result = await db.execute(
        select(models.Post).where(models.Post.id == shared_post.post_id)
    )
    original_post = post_result.scalars().first()

    reply_payload = {
        "type": "message",
        "id": reply_msg.id,
        "content": reply_msg.content,
        "sender_id": user_id,
        "receiver_id": payload.to,
        "timestamp": format_timestamp(reply_msg.created_at),
        "is_reply": True,
        "is_reply_to_share": True,
        "media_url":reply_msg.media_url,
        "media_type":reply_msg.media_type,
        "reply_to_share": {
            "shared_post_id": shared_post.id,
            "post_id": shared_post.post_id,
            "post_content": original_post.content[:100] + "..." if len(original_post.content) > 100 else original_post.content,
            "post_owner": original_post.user.username,
            "media_url": original_post.media_path  # if exists
        }
    }

    # Send to receiver (same logic as before)
    if payload.to in manager.active_connections:
        try:
            await manager.send_json_to_user(reply_payload,payload.to)
            await db.execute(
                update(models.Message)
                .where(models.Message.id == reply_msg.id, models.Message.is_read == False)
                .values(is_read=True, read_at=datetime.utcnow())
            )
            await db.commit()
        except:
            manager.disconnect(payload.to)
    # Send back to sender
    await manager.send_personal_message(reply_payload,user_id)