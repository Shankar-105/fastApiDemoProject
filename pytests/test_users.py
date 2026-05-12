async def test_signup_new_user(client):
    new_user = {
        "username": "alice",
        "password": "supersecurepw",
        "nickname": "Alice",
        "email": "alice@example.com",
    }
    resp = await client.post("/v1/users/register", json=new_user)
    assert resp.status_code in (201, 409)

async def test_get_all_users(client, get_token):
    resp = await client.get("/v1/users", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)