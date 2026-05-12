async def test_my_profile(client, get_token):
    resp = await client.get("/v1/users/me/profile", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"

async def test_update_user_info(client, get_token):
    resp = await client.patch("/v1/users/me", data={"bio": "updated bio"}, headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 200
