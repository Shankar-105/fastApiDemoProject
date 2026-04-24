from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import models

IDEMPOTENCY_TTL_HOURS = 24
PROCESSING_STALE_SECONDS = 120


@dataclass
class IdempotencyDecision:
    action: str  # process | replay | in_progress
    cached_response: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def begin_or_replay(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    idempotency_key: str,
) -> IdempotencyDecision:
    now = _utc_now()

    insert_stmt = (
        pg_insert(models.IdempotencyEvent)
        .values(
            user_id=user_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            status="processing",
            response_payload=None,
            expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        )
        .on_conflict_do_nothing(
            index_elements=[
                models.IdempotencyEvent.user_id,
                models.IdempotencyEvent.event_type,
                models.IdempotencyEvent.idempotency_key,
            ]
        )
    )
    insert_result = await db.execute(insert_stmt)

    if insert_result.rowcount and insert_result.rowcount > 0:
        await db.commit()
        return IdempotencyDecision(action="process")

    existing_result = await db.execute(
        select(models.IdempotencyEvent).where(
            models.IdempotencyEvent.user_id == user_id,
            models.IdempotencyEvent.event_type == event_type,
            models.IdempotencyEvent.idempotency_key == idempotency_key,
        )
    )
    existing = existing_result.scalars().first()

    if not existing:
        # Rare race; caller can retry with same key.
        return IdempotencyDecision(action="in_progress")

    if existing.status == "completed" and existing.response_payload is not None:
        return IdempotencyDecision(action="replay", cached_response=existing.response_payload)

    stale_before = now - timedelta(seconds=PROCESSING_STALE_SECONDS)
    takeover_result = await db.execute(
        update(models.IdempotencyEvent)
        .where(
            models.IdempotencyEvent.id == existing.id,
            models.IdempotencyEvent.status == "processing",
            models.IdempotencyEvent.created_at < stale_before,
        )
        .values(
            created_at=now,
            expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        )
    )

    if takeover_result.rowcount and takeover_result.rowcount > 0:
        await db.commit()
        return IdempotencyDecision(action="process")

    return IdempotencyDecision(action="in_progress")


async def complete(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    idempotency_key: str,
    response_payload: dict[str, Any],
) -> None:
    await db.execute(
        update(models.IdempotencyEvent)
        .where(
            models.IdempotencyEvent.user_id == user_id,
            models.IdempotencyEvent.event_type == event_type,
            models.IdempotencyEvent.idempotency_key == idempotency_key,
        )
        .values(
            status="completed",
            response_payload=response_payload,
            expires_at=_utc_now() + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        )
    )
    await db.commit()


async def release_processing_key(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    idempotency_key: str,
) -> None:
    await db.execute(
        delete(models.IdempotencyEvent).where(
            models.IdempotencyEvent.user_id == user_id,
            models.IdempotencyEvent.event_type == event_type,
            models.IdempotencyEvent.idempotency_key == idempotency_key,
            models.IdempotencyEvent.status == "processing",
        )
    )
    await db.commit()
