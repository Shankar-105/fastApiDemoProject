import asyncio
import uuid
from types import SimpleNamespace

from fastapi import HTTPException, Response

from app.services import redis_service
from app.services.idempotency_service import idempotent


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:10]


async def _post_twice(client, url: str, *, headers: dict, json=None, data=None, files=None):
    first = await client.post(url, headers=headers, json=json, data=data, files=files)
    second = await client.post(url, headers=headers, json=json, data=data, files=files)
    return first, second


async def test_idempotent_login_returns_same_tokens(client, create_test_user):
    payload = {
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    }
    headers = {"Idempotency-Key": str(uuid.uuid4())}

    first, second = await _post_twice(client, "/v1/auth/login", headers=headers, data=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["accessToken"] == second.json()["accessToken"]
    assert first.json()["refreshToken"] == second.json()["refreshToken"]


async def test_idempotent_create_post_returns_same_post(client, get_token):
    payload = {
        "title": f"Idempotent Post {_unique_suffix()}",
        "content": "This post should only be created once.",
    }
    headers = {
        "Authorization": f"Bearer {get_token}",
        "Idempotency-Key": str(uuid.uuid4()),
    }

    first, second = await _post_twice(client, "/v1/posts", headers=headers, data=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_requests_without_idempotency_key_still_work(client, get_token):
    response = await client.post(
        "/v1/posts",
        data={
            "title": f"Normal Post {_unique_suffix()}",
            "content": "This request intentionally has no idempotency key.",
        },
        headers={"Authorization": f"Bearer {get_token}"},
    )

    assert response.status_code == 201


class _FakeRedisClient:
    def __init__(self):
        self._store = {}
        self._lock = asyncio.Lock()

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        async with self._lock:
            if nx and key in self._store:
                return False
            self._store[key] = value
            return True

    async def delete(self, key):
        self._store.pop(key, None)


class _BrokenRedisClient:
    async def get(self, key):
        raise ConnectionError("redis unavailable")

    async def set(self, key, value, nx=False, ex=None):
        raise ConnectionError("redis unavailable")

    async def delete(self, key):
        raise ConnectionError("redis unavailable")


def _make_request(path: str = "/v1/items", method: str = "POST"):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


async def test_idempotent_conflict_when_same_key_has_different_payload(monkeypatch):
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(redis_service, "redis_client", fake_redis)

    calls = []

    @idempotent(endpoint_identifier="create_item", success_status_code=201)
    async def create_item(payload: dict, request=None, response=None, idempotency_key=None):
        calls.append(payload)
        return {"ok": True, "payload": payload}

    request = _make_request()
    first_response = Response()
    second_response = Response()

    first = await create_item(
        {"name": "alpha"},
        request=request,
        response=first_response,
        idempotency_key="fixed-key",
    )
    assert first == {"ok": True, "payload": {"name": "alpha"}}
    assert first_response.status_code == 201

    try:
        await create_item(
            {"name": "beta"},
            request=request,
            response=second_response,
            idempotency_key="fixed-key",
        )
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert len(calls) == 1


async def test_idempotent_rejects_concurrent_processing(monkeypatch):
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(redis_service, "redis_client", fake_redis)

    @idempotent(endpoint_identifier="slow_item", success_status_code=201)
    async def slow_item(payload: dict, request=None, response=None, idempotency_key=None):
        await asyncio.sleep(0.05)
        return {"ok": True, "payload": payload}

    request = _make_request(path="/v1/slow-items")

    async def invoke():
        return await slow_item(
            {"name": "alpha"},
            request=request,
            response=Response(),
            idempotency_key="shared-key",
        )

    results = await asyncio.gather(invoke(), invoke(), return_exceptions=True)
    assert any(isinstance(result, HTTPException) and result.status_code == 409 for result in results)
    assert sum(not isinstance(result, Exception) for result in results) == 1


async def test_idempotent_allows_request_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(redis_service, "redis_client", _BrokenRedisClient())

    @idempotent(endpoint_identifier="fallback_item", success_status_code=201)
    async def fallback_item(payload: dict, request=None, response=None, idempotency_key=None):
        return {"ok": True, "payload": payload}

    result = await fallback_item(
        {"name": "alpha"},
        request=_make_request(path="/v1/fallback-items"),
        response=Response(),
        idempotency_key="broken-redis-key",
    )

    assert result == {"ok": True, "payload": {"name": "alpha"}}
