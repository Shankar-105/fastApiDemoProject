from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app import models, schemas
from app.services import redis_service
from datetime import datetime
from app.utils.socket_manager import manager
import json
import structlog


logger = structlog.get_logger(__name__)

async def mark_as_read(payload: dict, reader_id: int, db: AsyncSession):
    """Mark all unread messages from a sender as read and broadcast receipt.

    Atomically updates all messages where sender_id == payload.sender_id and
    receiver_id == reader_id and is_read == False. Publishes a "read_receipt"
    event to Redis pub/sub with the count of messages affected, falling back
    to local WebSocket delivery. Also sends locally even on Redis success so
    tests and same-process feedback are immediate. Called from the WebSocket
    dispatch loop when type == "read_receipt".
    """
    try:
        sender_id = int(payload.get("sender_id"))
        logger.info("marking_messages_read", reader_id=reader_id, sender_id=sender_id)
        now = datetime.utcnow()
        # Atomic mark-read to avoid duplicate effects under concurrent receipts.
        update_result = await db.execute(
            update(models.Message)
            .where(
                models.Message.sender_id == sender_id,
                models.Message.receiver_id == reader_id,
                models.Message.is_read == False
            )
            .values(is_read=True, read_at=now)
            .returning(models.Message.id)
        )
        updated_message_ids = update_result.scalars().all()
        if not updated_message_ids:
            return

        await db.commit()
        
        receipt_payload = {
            "type": "read_receipt",
            "reader_id": reader_id,
            "read_at": str(now),
            "read_count": len(updated_message_ids),
            "conversation_with": reader_id,
            "receiver_id": sender_id
        }
        
        sender_payload = dict(receipt_payload)
        sender_payload["receiver_id"] = sender_id
        try:
            await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
            await redis_service.redis_client.publish("chat:messages", json.dumps(receipt_payload))
            logger.info("read_receipt_published_redis", reader_id=reader_id, sender_id=sender_id)
        except Exception as e:
            logger.warning("read_receipt_publish_redis_failed", reader_id=reader_id, sender_id=sender_id, error=str(e))
            try:
                await manager.send_personal_message(sender_payload, sender_id)
            except Exception:
                pass
        else:
            # Also send locally so tests and local feedback receive immediate delivery
            try:
                await manager.send_personal_message(sender_payload, sender_id)
            except Exception:
                pass
        
    except Exception as e:
        logger.exception("read_receipt_error", reader_id=reader_id, error=str(e))
