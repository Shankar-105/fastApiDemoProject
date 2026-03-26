async def test_login_success(client, create_test_user):
    data = {
        "username": "testuser",
        "password": "testpassword",
    }
    resp = await client.post("/login", data=data)
    assert resp.status_code == 202
    assert "accessToken" in resp.json()

async def test_login_wrong_password(client, create_test_user):
    data = {
        "username": "testuser",
        "password": "wrongpassword",
    }
    resp = await client.post("/login", data=data)
    assert resp.status_code == 401


async def test_login_unverified_email_blocked(client):
    payload = {
        "username": "unverified_user",
        "password": "testpassword",
        "nickname": "Unverified",
        "email": "unverified@example.com",
    }
    resp = await client.post("/user/signup", json=payload)
    assert resp.status_code == 201

    login = await client.post("/login", data={"username": payload["username"], "password": payload["password"]})
    assert login.status_code == 403


async def test_verify_email_then_login_works(client):
    payload = {
        "username": "verify_then_login",
        "password": "testpassword",
        "nickname": "VerifyMe",
        "email": "verify_then_login@example.com",
    }
    resp = await client.post("/user/signup", json=payload)
    assert resp.status_code == 201

    verify = await client.post("/verify-email", json={"email": payload["email"], "otp": "123456"})
    assert verify.status_code == 200

    login = await client.post("/login", data={"username": payload["username"], "password": payload["password"]})
    assert login.status_code == 202
    assert "accessToken" in login.json()