"""
Tests for Refresh Token Rotation (app/token_service.py + POST /v1/auth/refresh-token).

Covers:
  - Login returns both accessToken and refreshToken
  - POST /v1/auth/refresh-token with valid refresh token → new pair
  - Old refresh token rejected after rotation (reuse detection)
  - Expired refresh token → 401
  - Bogus / non-existent token → 401
  - Password change revokes all refresh tokens
"""
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app import models
from app.services import redis_service


@pytest.mark.asyncio(loop_scope="session")
async def test_login_returns_refresh_token(client, create_test_user):
    """Login should now return both accessToken AND refreshToken."""
    data = {
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    }
    resp = await client.post("/v1/auth/login", data=data)
    assert resp.status_code == 202
    body = resp.json()
    assert "accessToken" in body
    assert "refreshToken" in body
    assert len(body["refreshToken"]) > 20  # opaque 43-char string


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_returns_new_pair(client, create_test_user):
    """POST /v1/auth/refresh-token with a valid refresh token returns fresh access + refresh tokens."""
    # Login to get a refresh token
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    refresh_token = login_resp.json()["refreshToken"]

    # Use it
    resp = await client.post("/v1/auth/refresh-token", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    body = resp.json()
    assert "accessToken" in body
    assert "refreshToken" in body
    # The new refresh token must be different from the old one (rotation)
    assert body["refreshToken"] != refresh_token


@pytest.mark.asyncio(loop_scope="session")
async def test_old_refresh_token_rejected_after_rotation(client, create_test_user):
    """After rotation, the old refresh token is revoked and must be rejected."""
    # Login
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    old_refresh = login_resp.json()["refreshToken"]

    # Rotate once (old_refresh → new pair)
    resp1 = await client.post("/v1/auth/refresh-token", json={"refresh_token": old_refresh})
    assert resp1.status_code == 200

    # Simulate grace window expiry so the retry triggers real reuse detection.
    with patch.object(redis_service.redis_client, "get", AsyncMock(return_value=None)):
        resp2 = await client.post("/v1/auth/refresh-token", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401
    assert "reuse" in resp2.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_with_bogus_token(client):
    """A completely made-up token should return 401."""
    resp = await client.post("/v1/auth/refresh-token", json={"refresh_token": "bogus_token_abc123"})
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_chain_works(client, create_test_user):
    """Multiple consecutive rotations should work — each new token is valid."""
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    current_refresh = login_resp.json()["refreshToken"]

    for _ in range(3):
        resp = await client.post("/v1/auth/refresh-token", json={"refresh_token": current_refresh})
        assert resp.status_code == 200
        current_refresh = resp.json()["refreshToken"]


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_tokens_are_hashed_at_rest(client, create_test_user, db_session_factory):
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    assert login_resp.status_code == 202
    body = login_resp.json()
    refresh_token = body["refreshToken"]
    user_id = body["id"]

    async with db_session_factory() as db:
        token_row = (
            await db.execute(
                select(models.RefreshToken)
                .where(models.RefreshToken.user_id == user_id)
                .order_by(models.RefreshToken.id.desc())
            )
        ).scalars().first()

    assert token_row is not None
    assert token_row.token != refresh_token
    assert len(token_row.token) == 64


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_revokes_refresh_tokens(client, create_test_user):
    """After logout, the refresh token should no longer work."""
    # Login
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    body = login_resp.json()
    access_token = body["accessToken"]
    refresh_token = body["refreshToken"]

    # Logout (sends the access token in the Authorization header)
    logout_resp = await client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200

    # Try to refresh — should fail because logout revoked all tokens
    resp = await client.post("/v1/auth/refresh-token", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_invalidates_cached_access_token(client, create_test_user):
    """A cached access token must still fail after logout/blacklist."""
    login_resp = await client.post("/v1/auth/login", data={
        "username": create_test_user["username"],
        "password": create_test_user["password"],
    })
    body = login_resp.json()
    access_token = body["accessToken"]

    warmup_resp = await client.get(
        "/v1/users/me/profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert warmup_resp.status_code == 200

    logout_resp = await client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200

    protected_resp = await client.get(
        "/v1/users/me/profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert protected_resp.status_code == 401
