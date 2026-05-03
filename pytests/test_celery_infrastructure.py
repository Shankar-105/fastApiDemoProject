from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.celery_app import celery_app
from app.routes import celery_tasks


@dataclass
class FakeAsyncResult:
    state: str
    result: object = None
    info: object = None
    traceback: str | None = None


class FakeInspector:
    def __init__(self, active=None, reserved=None, stats=None):
        self._active = active
        self._reserved = reserved
        self._stats = stats

    def active(self):
        return self._active

    def reserved(self):
        return self._reserved

    def stats(self):
        return self._stats


@pytest.mark.asyncio
async def test_celery_queue_and_beat_configuration():
    queue_names = {queue.name for queue in celery_app.conf.task_queues}
    assert "celery" in queue_names
    assert "dead_letter_queue" in queue_names

    main_queue = next(queue for queue in celery_app.conf.task_queues if queue.name == "celery")
    assert main_queue.queue_arguments["x-dead-letter-exchange"] == "dead_letter_exchange"

    dlq = next(queue for queue in celery_app.conf.task_queues if queue.name == "dead_letter_queue")
    assert dlq.exchange.name == "dead_letter_exchange"
    assert dlq.routing_key == "dead_letter"

    schedule = celery_app.conf.beat_schedule["cleanup-expired-otps"]
    assert schedule["task"] == "app.tasks.otp_cleanup_task.cleanup_expired_otps"
    assert schedule["options"]["queue"] == "celery"
    assert 0 in schedule["schedule"].minute


@pytest.mark.asyncio
async def test_task_status_endpoint_states(monkeypatch):
    monkeypatch.setattr(celery_tasks, "AsyncResult", lambda task_id, app=None: FakeAsyncResult(state="SUCCESS", result={"ok": True}))
    success = await celery_tasks.get_task_status("task-1")
    assert success["status"] == "SUCCESS"
    assert success["progress"] == 100
    assert success["result"] == {"ok": True}

    monkeypatch.setattr(
        celery_tasks,
        "AsyncResult",
        lambda task_id, app=None: FakeAsyncResult(state="FAILURE", info=RuntimeError("boom"), traceback="traceback-line"),
    )
    failure = await celery_tasks.get_task_status("task-2")
    assert failure["status"] == "FAILURE"
    assert failure["progress"] == 0
    assert failure["traceback"] == "traceback-line"

    monkeypatch.setattr(
        celery_tasks,
        "AsyncResult",
        lambda task_id, app=None: FakeAsyncResult(state="RETRY", info={"exc_message": "temporary issue"}),
    )
    retry = await celery_tasks.get_task_status("task-3")
    assert retry["status"] == "RETRY"
    assert "temporary issue" in retry["result"]


@pytest.mark.asyncio
async def test_task_listing_endpoints(monkeypatch):
    inspector = FakeInspector(
        active={
            "worker-1": [
                {"id": "a1", "name": "app.tasks.email_tasks.send_otp_email", "args": ["me@example.com"], "time_start": 10.5}
            ]
        },
        reserved={
            "worker-1": [
                {"id": "r1", "name": "app.tasks.otp_cleanup_task.cleanup_expired_otps", "args": []}
            ]
        },
        stats={
            "worker-1": {
                "pool": {"max-concurrency": 1},
                "total": 42,
                "broker": {"transport": "amqp"},
            }
        },
    )
    monkeypatch.setattr(celery_tasks.celery_app.control, "inspect", lambda: inspector)

    active = await celery_tasks.get_active_tasks()
    assert active["count"] == 1
    assert active["active_tasks"][0]["task_name"] == "app.tasks.email_tasks.send_otp_email"

    reserved = await celery_tasks.get_reserved_tasks()
    assert reserved["count"] == 1
    assert reserved["reserved_tasks"][0]["task_id"] == "r1"

    stats = await celery_tasks.get_worker_stats()
    assert stats["workers"]["worker-1"]["processed_tasks"] == 42
    assert stats["workers"]["worker-1"]["broker_transport"] == "amqp"


@pytest.mark.asyncio
async def test_revoke_and_purge_controls(monkeypatch):
    calls = SimpleNamespace(revoke=None, purge=False)

    def fake_revoke(task_id, terminate=False):
        calls.revoke = (task_id, terminate)

    def fake_purge():
        calls.purge = True

    monkeypatch.setattr(celery_tasks.celery_app.control, "revoke", fake_revoke)
    monkeypatch.setattr(celery_tasks.celery_app.control, "purge", fake_purge)

    revoke_response = await celery_tasks.revoke_task("task-99", terminate=True)
    assert revoke_response["terminated"] is True
    assert calls.revoke == ("task-99", True)

    purge_response = await celery_tasks.purge_queue("celery")
    assert purge_response["message"] == "Queue 'celery' purged successfully"
    assert calls.purge is True
