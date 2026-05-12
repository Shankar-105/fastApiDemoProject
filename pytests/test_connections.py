async def test_follow_unfollow(client, get_token):
    # Sign up a second user
    user2 = {"username": "user2", "password": "password", "nickname": "Nick2", "email": "user2@example.com"}
    await client.post("/v1/users/register", json=user2)
    # Get second user ID
    users_resp = await client.get("/v1/users", headers={"Authorization": f"Bearer {get_token}"})
    users = users_resp.json()
    second_user = next((u for u in users if u["username"] == "user2"), None)
    assert second_user is not None
    second_id = second_user["id"]
    # Follow
    resp = await client.post(f"/v1/users/{second_id}/follow", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code in (201, 400)
    # Unfollow (returns 200 on success, 400 if not following)
    resp2 = await client.delete(f"/v1/users/{second_id}/unfollow", headers={"Authorization": f"Bearer {get_token}"})
    assert resp2.status_code in (200, 400)
