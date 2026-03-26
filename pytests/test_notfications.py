# helpers

async def signup_and_login(client, username: str, password: str = "password123") -> str:
    """Create a fresh user and return their access token."""
    email = f"{username}@example.com"
    await client.post("/user/signup", json={
        "username": username,
        "password": password,
        "nickname": username,
        "email": email,
    })
    verify = await client.post("/verify-email", json={"email": email, "otp": "123456"})
    assert verify.status_code == 200, f"verify failed for {username}: {verify.text}"
    login = await client.post("/login", data={"username": username, "password": password})
    assert login.status_code == 202, f"login failed for {username}: {login.text}"
    return login.json()["accessToken"]


# empty-state tests (main test user has no notifications yet)

async def test_get_notifications_empty(client, get_token):
    """Fresh test user starts with zero notifications."""
    resp = await client.get(
        "/me/notifications",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["notifications"], list)
    assert data["unread_count"] == 0
    assert data["total"] == 0
    assert data["has_more"] is False


async def test_unread_count_empty(client, get_token):
    """Unread badge should be 0 for a user with no notifications."""
    resp = await client.get(
        "/me/notifications/unread-count",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_mark_read_is_idempotent_when_empty(client, get_token):
    """PATCH /me/notifications/read should succeed even with 0 notifications."""
    resp = await client.patch(
        "/me/notifications/read",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "All notifications marked as read"


# like trigger creates notification

async def test_like_creates_notification(client, get_token):
    """
    User A (get_token = testuser) likes User B's post.
    A notification of type 'like' must appear in User B's feed.
    """
    # Create User B and their post
    token_b = await signup_and_login(client, "notif_b_like")
    post_resp = await client.post(
        "/posts/createPost",
        data={"title": "B like test post", "content": "hi"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    # User A likes it
    like_resp = await client.post(
        "/vote/on_post",
        json={"post_id": post_id, "choice": True},
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert like_resp.status_code == 201

    # User B should have a 'like' notification
    notifs = await client.get(
        "/me/notifications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert notifs.status_code == 200
    data = notifs.json()
    assert data["unread_count"] >= 1
    types = [n["type"] for n in data["notifications"]]
    assert "like" in types


# comment trigger creates notification

async def test_comment_creates_notification(client, get_token):
    """
    User A comments on User B's post.
    A notification of type 'comment' must appear in User B's feed.
    """
    token_b = await signup_and_login(client, "notif_b_comment")
    post_resp = await client.post(
        "/posts/createPost",
        data={"title": "B comment test post", "content": "hi"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    # User A comments
    comment_resp = await client.post(
        f"/comment/createComment",
        json={"post_id":post_id,"content": "nice post!"},
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert comment_resp.status_code == 201

    notifs = await client.get(
        "/me/notifications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    data = notifs.json()
    assert data["unread_count"] >= 1
    assert any(n["type"] == "comment" for n in data["notifications"])

# follow trigger creates notification

async def test_follow_creates_notification(client, get_token):
    """
    User A (testuser) follows User B.
    A notification of type 'follow' must appear in User B's feed.
    """
    token_b = await signup_and_login(client, "notif_b_follow")

    # Get User B's id
    users_resp = await client.get(
        "/users/getAllUsers",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    users = users_resp.json()
    user_b = next((u for u in users if u["username"] == "notif_b_follow"), None)
    assert user_b is not None

    follow_resp = await client.post(
        f"/follow/{user_b['id']}",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert follow_resp.status_code in (201, 400)  # 400 = already following

    notifs = await client.get(
        "/me/notifications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    data = notifs.json()
    assert any(n["type"] == "follow" for n in data["notifications"])


# no self-notification

async def test_no_self_notification_on_own_post_like(client, get_token):
    """
    Liking your own post must NOT create a notification.
    """
    post_resp = await client.post(
        "/posts/createPost",
        data={"title": "self like test", "content": "mine"},
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    # Check count before
    before = await client.get(
        "/me/notifications/unread-count",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    before_count = before.json()["count"]

    # Like own post
    await client.post(
        "/vote/on_post",
        json={"post_id": post_id, "choice": True},
        headers={"Authorization": f"Bearer {get_token}"},
    )

    # Count must not increase
    after = await client.get(
        "/me/notifications/unread-count",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert after.json()["count"] == before_count


# mark-read clears badge

async def test_mark_read_clears_badge(client, get_token):
    """
    After PATCH /me/notifications/read, unread count goes to 0.
    We use User B from the like test to ensure there's something to clear.
    """
    # Create a fresh user B, give them a notification first
    token_b = await signup_and_login(client, "notif_b_markread")
    post_resp = await client.post(
        "/posts/createPost",
        data={"title": "markread test post", "content": "hi"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    post_id = post_resp.json()["id"]

    # User A likes → notification for B
    await client.post(
        "/vote/on_post",
        json={"post_id": post_id, "choice": True},
        headers={"Authorization": f"Bearer {get_token}"},
    )

    # Confirm B has unread
    before = await client.get(
        "/me/notifications/unread-count",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert before.json()["count"] >= 1

    # Mark all read
    mark = await client.patch(
        "/me/notifications/read",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert mark.status_code == 200

    # Badge should now be 0
    after = await client.get(
        "/me/notifications/unread-count",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert after.json()["count"] == 0

    # All notifications are still there, just marked read
    all_notifs = await client.get(
        "/me/notifications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    data = all_notifs.json()
    assert data["total"] >= 1                                          # still exist
    assert all(n["is_read"] is True for n in data["notifications"])   # all read


# pagination sanity check

async def test_notifications_pagination(client, get_token):
    """limit/offset parameters are respected."""
    resp = await client.get(
        "/me/notifications?limit=1&offset=0",
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["notifications"]) <= 1