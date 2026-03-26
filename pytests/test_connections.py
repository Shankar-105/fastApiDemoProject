async def test_follow_unfollow(client, get_token):
    # Sign up a second user
    user2 = {"username": "user2", "password": "password", "nickname": "Nick2", "email": "user2@example.com"}
    await client.post("/user/signup", json=user2)
    # Get second user ID
    users_resp = await client.get("/users/getAllUsers", headers={"Authorization": f"Bearer {get_token}"})
    users = users_resp.json()
    second_user = next((u for u in users if u["username"] == "user2"), None)
    assert second_user is not None
    second_id = second_user["id"]
    # Follow
    resp = await client.post(f"/follow/{second_id}", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code in (201, 400)
    # Unfollow (returns 200 on success, 400 if not following)
    resp2 = await client.delete(f"/unfollow/{second_id}", headers={"Authorization": f"Bearer {get_token}"})
    assert resp2.status_code in (200, 400)