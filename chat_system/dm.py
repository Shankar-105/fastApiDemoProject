from fastapi import APIRouter, WebSocket, WebSocketDisconnect,Depends,Query
from app import schemas, models, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.my_utils.socket_manager import manager
from app.my_utils.time_formatting import format_timestamp
from app.services import redis_service
from datetime import datetime
import json
               
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
        
        # Publish to Redis for cross-process delivery
        try:
            await redis_service.redis_client.publish(
                "chat:messages",
                json.dumps(reply_payload)
            )
            print("Message published to Redis for cross-process delivery")
        except Exception as e:
            print(f"Failed to publish to Redis: {e}")
        
        # Check if receiver is in active_connections (local process)
        receiver_id = msg.receiver_id
        if receiver_id in manager.active_connections:
            try:
                # Try to send (if fails, it's a zombie)
                await manager.send_json_to_user(reply_payload,payload.to)
                print("Message sent via WebSocket (local process)")
                await db.execute(
                    update(models.Message)
                    .where(models.Message.id == msg.id, models.Message.is_read == False)
                    .values(is_read=True, read_at=datetime.utcnow())
                )
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