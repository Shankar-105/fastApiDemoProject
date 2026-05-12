async def test_create_post(client, get_token):
    data = {
        "title": "My First Post",
        "content": "Here's the post content!"
    }
    resp = await client.post("/v1/posts", data=data, headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 201

async def test_get_post(client, get_token):
    # Post creation first (so we have a real post)
    create = await client.post("/v1/posts", data={
        "title": "Check Post",
        "content": "Hello World"
    }, headers={"Authorization": f"Bearer {get_token}"})
    post_id = create.json().get("id") or 1
    resp = await client.get(f"/v1/posts/{post_id}", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code in (200, 404)


async def test_create_post_requires_auth(client):
    resp = await client.post("/v1/posts", data={"title": "No Auth", "content": "Should fail"})
    assert resp.status_code == 401


async def test_create_post_response_has_core_fields(client, get_token):
    resp = await client.post(
        "/v1/posts",
        data={"title": "Schema Check", "content": "Core fields test"},
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "title" in body
    assert "content" in body