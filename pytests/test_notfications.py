# empty-state tests (main test user has no notifications yet)

async def test_get_notifications_empty(client, get_token):
    """Fresh test user starts with zero notifications."""
    resp = await client.get(
        "/v1/users/me/notifications",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["notifications"], list)
    assert data["unread_count"] == 0
    assert data["total"] == 0
    assert data["has_more"] is False


async def test_mark_read_is_idempotent_when_empty(client, get_token):
    """PATCH /v1/users/me/notifications/read should succeed even with 0 notifications."""
    resp = await client.patch(
        "/v1/users/me/notifications/read",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "All notifications marked as read"
async def test_notifications_requires_auth(client):
    resp = await client.get("/v1/users/me/notifications")
    assert resp.status_code == 401
