from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import models
from app.services import idempotency_service


@pytest.mark.asyncio
async def test_idempotency_replays_completed_response(db_session_factory):
    async with db_session_factory() as db:
        user = models.User(
            username="idem_u1",
            password="x",
            nickname="idem",
            email="idem_u1@example.com",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with db_session_factory() as db:
        first = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="reaction",
            idempotency_key="k1",
        )
    assert first.action == "process"

    expected = {"status": "ok", "result": {"value": 1}}
    async with db_session_factory() as db:
        await idempotency_service.complete(
            db,
            user_id=user_id,
            event_type="reaction",
            idempotency_key="k1",
            response_payload=expected,
        )

    async with db_session_factory() as db:
        second = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="reaction",
            idempotency_key="k1",
        )
    assert second.action == "replay"
    assert second.cached_response == expected


@pytest.mark.asyncio
async def test_idempotency_in_progress_before_completion(db_session_factory):
    async with db_session_factory() as db:
        user = models.User(
            username="idem_u2",
            password="x",
            nickname="idem",
            email="idem_u2@example.com",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with db_session_factory() as db:
        first = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="delete_for_everyone",
            idempotency_key="k2",
        )
    assert first.action == "process"

    async with db_session_factory() as db:
        second = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="delete_for_everyone",
            idempotency_key="k2",
        )
    assert second.action == "in_progress"


@pytest.mark.asyncio
async def test_idempotency_stale_processing_can_be_taken_over(db_session_factory):
    async with db_session_factory() as db:
        user = models.User(
            username="idem_u3",
            password="x",
            nickname="idem",
            email="idem_u3@example.com",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with db_session_factory() as db:
        first = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="reply_message",
            idempotency_key="k3",
        )
    assert first.action == "process"

    async with db_session_factory() as db:
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=idempotency_service.PROCESSING_STALE_SECONDS + 10)
        await db.execute(
            models.IdempotencyEvent.__table__.update()
            .where(
                models.IdempotencyEvent.user_id == user_id,
                models.IdempotencyEvent.event_type == "reply_message",
                models.IdempotencyEvent.idempotency_key == "k3",
            )
            .values(created_at=stale_time)
        )
        await db.commit()

    async with db_session_factory() as db:
        second = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="reply_message",
            idempotency_key="k3",
        )
    assert second.action == "process"


@pytest.mark.asyncio
async def test_idempotency_release_processing_key(db_session_factory):
    async with db_session_factory() as db:
        user = models.User(
            username="idem_u4",
            password="x",
            nickname="idem",
            email="idem_u4@example.com",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with db_session_factory() as db:
        first = await idempotency_service.begin_or_replay(
            db,
            user_id=user_id,
            event_type="read_receipt",
            idempotency_key="k4",
        )
    assert first.action == "process"

    async with db_session_factory() as db:
        await idempotency_service.release_processing_key(
            db,
            user_id=user_id,
            event_type="read_receipt",
            idempotency_key="k4",
        )

    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(models.IdempotencyEvent).where(
                    models.IdempotencyEvent.user_id == user_id,
                    models.IdempotencyEvent.event_type == "read_receipt",
                    models.IdempotencyEvent.idempotency_key == "k4",
                )
            )
        ).scalars().first()

    assert row is None
