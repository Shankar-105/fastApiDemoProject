from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models,oauth2,db
from app.utils.time_formatting import format_timestamp

router = APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

@router.get("/messages/{msg_id}")
async def get_message_info(
    msg_id: int,
    db: AsyncSession = Depends(db.getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser)
):
    """Return delivery and read-receipt info for a single message.

    Only the sender or receiver of the message may access this endpoint.
    Returns the creation timestamp (delivered_at), read timestamp (if read),
    and a boolean is_read flag. Called from the message info/details UI.
    """
    result = await db.execute(
        select(models.Message).where(models.Message.id == msg_id)
    )
    msg = result.scalars().first()
    if not msg:
        raise HTTPException(404, "Message not found")
    
    # Only sender or receiver can see info
    if msg.sender_id != currentUser.id and msg.receiver_id != currentUser.id:
        raise HTTPException(403,"Not authorized")
    # simple message information
    return {
        "message_id": msg.id,
        "delivered_at": format_timestamp(msg.created_at),
        "read_at": format_timestamp(msg.read_at) if msg.read_at else None,
        "is_read": msg.is_read
    }
