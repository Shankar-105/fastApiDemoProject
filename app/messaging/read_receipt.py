from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app import models, schemas
from app.services import redis_service
from datetime import datetime
from app.utils.socket_manager import manager
import json
import logging


logger = logging.getLogger("app")

async def mark_as_read(payload: dict, reader_id: int, db: AsyncSession):
    try:
        sender_id = int(payload.get("sender_id"))
        logger.info("Marking messages as read", extra={"extra_info": {"reader_id": reader_id, "sender_id": sender_id}})
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
            logger.info("Read receipt published to Redis", extra={"extra_info": {"reader_id": reader_id, "sender_id": sender_id}})
        except Exception as e:
            logger.warning("Failed to publish read receipt to Redis", extra={"extra_info": {"reader_id": reader_id, "sender_id": sender_id, "error": str(e)}})
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
        logger.exception("Error in read_receipt", extra={"extra_info": {"reader_id": reader_id, "error": str(e)}})
