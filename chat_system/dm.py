from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from app.my_utils.socket_manager import manager
from app.my_utils.time_formatting import format_timestamp
from datetime import datetime
               
async def messageUser(
    payload:schemas.MessageSchema,
    user_id:int,
    db:AsyncSession
):    
        msg = models.Message(
        content=payload.content,
        sender_id=user_id,
        receiver_id=payload.to,
        media_type=payload.media_type,
        media_url=payload.media_url
    )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        print("added to db")
        
        reply_payload = {
        "id": msg.id,
        "content": msg.content,
        "media_url":msg.media_url,
        "media_type":msg.media_type,
        "sender_id": user_id,
        "receiver_id": payload.to,
        "type": "message",
        "timestamp": format_timestamp(msg.created_at),
        "is_reply": False,
        "is_reply_to_share": False,
    }
        # Check if receiver is in active_connections
        receiver_id = msg.receiver_id
        if receiver_id in manager.active_connections:
            try:
                # Try to send (if fails, it's a zombie)
                await manager.send_json_to_user(reply_payload,payload.to)
                print("Message sent via WebSocket")
                msg.is_read = True
                msg.read_at=datetime.utcnow()
                await db.commit()
                print(f"Message {msg.id} marked as READ")
            except Exception as e:
                # Send failed → zombie socket → remove
                print(f"Send failed: {e}")
                manager.disconnect(receiver_id)
                # TODO: Later, send push notification here
        else:
            # Offline → don't send, just save in DB
            print("Receiver offline — message saved in DB")
            # TODO: Later, send push notification here
        # Send response back to sender
        await manager.send_personal_message(reply_payload,user_id)
        print("Response sent to sender")