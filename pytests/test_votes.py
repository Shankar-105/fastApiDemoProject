async def test_vote_on_post(client, get_token):
    # Create post first
    create = await client.post("/v1/posts", data={
        "title": "Like this Post",
        "content": "Like content"
    }, headers={"Authorization": f"Bearer {get_token}"})
    post_id = create.json().get("id") or 1
    vote = {"post_id": post_id, "choice": True}
    resp = await client.post(f"/v1/posts/{vote['post_id']}/votes", json=vote, headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 201

async def test_vote_on_nonexistent_post(client,get_token):
    vote = {"post_id": 69420, "choice": True}
    resp = await client.post(f"/v1/posts/{vote['post_id']}/votes", json=vote, headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 404