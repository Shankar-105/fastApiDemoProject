import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app import models
from app.routes import connect
from app.services.concurrency_service import run_with_transient_retry
from app.services.reconciliation_service import reconcile_denormalized_counters
from chat_system import delete_msg, load_missed_msgs, read_receipt


async def _seed_chat_users(session_factory):
    nonce = uuid.uuid4().hex[:8]
    async with session_factory() as db:
        sender = models.User(
            username=f"cc_sender_{nonce}",
            password="x",
            nickname="sender",
            email=f"cc_sender_{nonce}@example.com",
        )
        receiver = models.User(
            username=f"cc_receiver_{nonce}",
            password="x",
            nickname="receiver",
            email=f"cc_receiver_{nonce}@example.com",
        )
        db.add_all([sender, receiver])
        await db.commit()
        await db.refresh(sender)
        await db.refresh(receiver)
        return sender.id, receiver.id


@pytest.mark.asyncio
async def test_read_receipt_is_idempotent_under_concurrency(db_session_factory, monkeypatch):
    sender_id, receiver_id = await _seed_chat_users(db_session_factory)

    async with db_session_factory() as db:
        db.add_all(
            [
                models.Message(
                    content=f"m-{i}",
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    is_read=False,
                    media_type="false",
                    media_url="false",
                )
                for i in range(4)
            ]
        )
        await db.commit()

    send_mock = AsyncMock()
    monkeypatch.setattr(read_receipt.manager, "send_personal_message", send_mock)

    async def _run_once():
        async with db_session_factory() as db:
            await read_receipt.mark_as_read({"sender_id": sender_id}, receiver_id, db)

    await asyncio.gather(_run_once(), _run_once())

    async with db_session_factory() as db:
        result = await db.execute(
            select(models.Message).where(
                models.Message.sender_id == sender_id,
                models.Message.receiver_id == receiver_id,
            )
        )
        messages = result.scalars().all()

    assert len(messages) == 4
    assert all(m.is_read for m in messages)
    assert all(m.read_at is not None for m in messages)
    assert send_mock.await_count == 1


@pytest.mark.asyncio
async def test_load_missed_claims_each_message_once(db_session_factory):
    sender_id, receiver_id = await _seed_chat_users(db_session_factory)

    async with db_session_factory() as db:
        db.add_all(
            [
                models.Message(
                    content=f"claim-{i}",
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    is_read=False,
                    media_type="false",
                    media_url="false",
                )
                for i in range(6)
            ]
        )
        await db.commit()

    async def _load_once():
        async with db_session_factory() as db:
            return await load_missed_msgs.load_missed_content(receiver_id, db)

    first_batch, second_batch = await asyncio.gather(_load_once(), _load_once())

    first_ids = {item["id"] for item in first_batch if item.get("type") == "message"}
    second_ids = {item["id"] for item in second_batch if item.get("type") == "message"}

    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == 6


@pytest.mark.asyncio
async def test_delete_for_everyone_is_single_transition(db_session_factory, monkeypatch):
    sender_id, receiver_id = await _seed_chat_users(db_session_factory)

    async with db_session_factory() as db:
        message = models.Message(
            content="to-delete",
            sender_id=sender_id,
            receiver_id=receiver_id,
            media_type="false",
            media_url="false",
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        message_id = message.id

    send_receiver = AsyncMock()
    send_sender = AsyncMock()
    monkeypatch.setattr(delete_msg.manager, "send_json_to_user", send_receiver)
    monkeypatch.setattr(delete_msg.manager, "send_personal_message", send_sender)

    async def _delete_once():
        async with db_session_factory() as db:
            await delete_msg.delete_for_everyone(db, message_id, sender_id, receiver_id)

    await asyncio.gather(_delete_once(), _delete_once())

    async with db_session_factory() as db:
        result = await db.execute(select(models.Message).where(models.Message.id == message_id))
        row = result.scalars().first()

    assert row is not None
    assert row.is_deleted_for_everyone is True
    assert send_receiver.await_count == 1
    assert send_sender.await_count == 1


@pytest.mark.asyncio
async def test_follow_is_atomic_under_concurrency(db_session_factory):
    nonce = uuid.uuid4().hex[:8]
    async with db_session_factory() as db:
        follower = models.User(
            username=f"follow_src_{nonce}",
            password="x",
            nickname="follower",
            email=f"follow_src_{nonce}@example.com",
        )
        followed = models.User(
            username=f"follow_dst_{nonce}",
            password="x",
            nickname="followed",
            email=f"follow_dst_{nonce}@example.com",
        )
        db.add_all([follower, followed])
        await db.commit()
        await db.refresh(follower)
        await db.refresh(followed)
        follower_id = follower.id
        followed_id = followed.id

    async def _follow_once():
        async with db_session_factory() as db:
            follower_row = (await db.execute(select(models.User).where(models.User.id == follower_id))).scalars().first()
            assert follower_row is not None
            return await connect.follow(
                followed_id,
                db=db,
                currentUser=follower_row,
                background_tasks=BackgroundTasks(),
                _=None,
            )

    results = await asyncio.gather(_follow_once(), _follow_once(), return_exceptions=True)
    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, HTTPException)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 400

    async with db_session_factory() as db:
        follower_row = (await db.execute(select(models.User).where(models.User.id == follower_id))).scalars().first()
        followed_row = (await db.execute(select(models.User).where(models.User.id == followed_id))).scalars().first()
        connection_count = (
            await db.execute(
                select(func.count()).select_from(models.connections).where(
                    models.connections.c.followed_id == followed_id,
                    models.connections.c.follower_id == follower_id,
                )
            )
        ).scalar_one()

    assert follower_row is not None
    assert followed_row is not None
    assert follower_row.following_cnt == 1
    assert followed_row.followers_cnt == 1
    assert connection_count == 1


@pytest.mark.asyncio
async def test_reconciliation_repairs_counter_drift(db_session_factory):
    async with db_session_factory() as db:
        u1 = models.User(
            username="rc_u1",
            password="x",
            nickname="u1",
            email="rc_u1@example.com",
            followers_cnt=33,
            following_cnt=44,
        )
        u2 = models.User(
            username="rc_u2",
            password="x",
            nickname="u2",
            email="rc_u2@example.com",
            followers_cnt=55,
            following_cnt=66,
        )
        db.add_all([u1, u2])
        await db.flush()
        u1_id = u1.id
        u2_id = u2.id

        post = models.Post(
            title="t",
            content="c",
            user_id=u1.id,
            likes=99,
            dis_likes=88,
            views=77,
            comments_cnt=66,
        )
        db.add(post)
        await db.flush()
        post_id = post.id

        msg = models.Message(
            content="hi",
            sender_id=u1.id,
            receiver_id=u2.id,
            reaction_cnt=9,
            media_type="false",
            media_url="false",
        )
        db.add(msg)
        await db.flush()
        msg_id = msg.id

        share = models.SharedPost(post_id=post.id, from_user_id=u1.id, to_user_id=u2.id, reaction_cnt=7)
        db.add(share)
        await db.flush()
        share_id = share.id

        comment = models.Comments(post_id=post.id, user_id=u1.id, comment_content="one", likes=12)
        db.add(comment)
        await db.flush()
        comment_id = comment.id

        db.add_all(
            [
                models.PostView(post_id=post.id, user_id=u1.id),
                models.PostView(post_id=post.id, user_id=u2.id),
                models.Votes(post_id=post.id, user_id=u1.id, action=True),
                models.Votes(post_id=post.id, user_id=u2.id, action=False),
                models.CommentVotes(comment_id=comment.id, user_id=u2.id, like=True),
                models.MessageReaction(message_id=msg.id, user_id=u1.id, reaction="🔥"),
                models.SharedPostReaction(shared_post_id=share.id, user_id=u2.id, reaction="❤️"),
            ]
        )
        await db.execute(
            models.connections.insert().values(followed_id=u2.id, follower_id=u1.id)
        )
        await db.commit()

    async with db_session_factory() as db:
        repaired = await reconcile_denormalized_counters(db)

    assert repaired["message_reaction_cnt"] >= 1
    assert repaired["shared_post_reaction_cnt"] >= 1
    assert repaired["user_following_cnt"] >= 1
    assert repaired["user_followers_cnt"] >= 1
    assert repaired["comment_likes"] >= 1
    assert repaired["post_comments_cnt"] >= 1
    assert repaired["post_views"] >= 1
    assert repaired["post_likes"] >= 1
    assert repaired["post_dislikes"] >= 1

    async with db_session_factory() as db:
        post_row = (await db.execute(select(models.Post).where(models.Post.id == post_id))).scalars().first()
        comment_row = (await db.execute(select(models.Comments).where(models.Comments.id == comment_id))).scalars().first()
        msg_row = (await db.execute(select(models.Message).where(models.Message.id == msg_id))).scalars().first()
        share_row = (await db.execute(select(models.SharedPost).where(models.SharedPost.id == share_id))).scalars().first()
        u1_row = (await db.execute(select(models.User).where(models.User.id == u1_id))).scalars().first()
        u2_row = (await db.execute(select(models.User).where(models.User.id == u2_id))).scalars().first()

    assert post_row is not None
    assert comment_row is not None
    assert msg_row is not None
    assert share_row is not None
    assert u1_row is not None
    assert u2_row is not None
    assert post_row.comments_cnt == 1
    assert post_row.views == 2
    assert post_row.likes == 1
    assert post_row.dis_likes == 1
    assert comment_row.likes == 1
    assert msg_row.reaction_cnt == 1
    assert share_row.reaction_cnt == 1
    assert u1_row.following_cnt == 1
    assert u2_row.followers_cnt == 1


@pytest.mark.asyncio
async def test_user_versioning_rejects_stale_update(db_session_factory):
    nonce = uuid.uuid4().hex[:8]
    async with db_session_factory() as db:
        user = models.User(
            username=f"ver_{nonce}",
            password="x",
            nickname="versioned",
            email=f"ver_{nonce}@example.com",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with db_session_factory() as first_db, db_session_factory() as second_db:
        first_user = (await first_db.execute(select(models.User).where(models.User.id == user_id))).scalars().first()
        second_user = (await second_db.execute(select(models.User).where(models.User.id == user_id))).scalars().first()
        assert first_user is not None
        assert second_user is not None

        first_user.nickname = "first"
        await first_db.commit()

        second_user.nickname = "second"
        with pytest.raises(StaleDataError):
            await second_db.commit()


@pytest.mark.asyncio
async def test_transient_retry_retries_once_and_returns_value():
    state = {"calls": 0}

    class FakeOrig:
        sqlstate = "40001"

    async def operation():
        state["calls"] += 1
        if state["calls"] == 1:
            raise OperationalError("update users", {}, FakeOrig())
        return "ok"

    result = await run_with_transient_retry(operation, attempts=3, base_delay=0, max_delay=0)

    assert result == "ok"
    assert state["calls"] == 2
