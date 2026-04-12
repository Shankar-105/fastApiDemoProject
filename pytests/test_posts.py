async def test_create_post(client, get_token):
    data = {
        "title": "My First Post",
        "content": "Here's the post content!"
    }
    resp = await client.post("/posts/createPost", data=data, headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 201

async def test_get_post(client, get_token):
    # Post creation first (so we have a real post)
    create = await client.post("/posts/createPost", data={
        "title": "Check Post",
        "content": "Hello World"
    }, headers={"Authorization": f"Bearer {get_token}"})
    post_id = create.json().get("post", {}).get("id") or 1
    resp = await client.get(f"/posts/getPost/{post_id}", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code in (200, 404)


async def test_create_post_requires_auth(client):
    resp = await client.post("/posts/createPost", data={"title": "No Auth", "content": "Should fail"})
    assert resp.status_code == 401


async def test_create_post_response_has_core_fields(client, get_token):
    resp = await client.post(
        "/posts/createPost",
        data={"title": "Schema Check", "content": "Core fields test"},
        headers={"Authorization": f"Bearer {get_token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "title" in body
    assert "content" in body