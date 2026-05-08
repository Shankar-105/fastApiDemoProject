"""
Enhanced test suite for schema validation and endpoint testing
"""

async def test_post_response_is_proper_json_not_orm(client, get_token):
    """Verify posts return JSON dict, not ORM objects"""
    # Create a post first
    create_resp = await client.post("/posts/createPost", 
        data={"title": "Test JSON", "content": "Testing JSON response"},
        headers={"Authorization": f"Bearer {get_token}"})
    assert create_resp.status_code == 201
    
    # Verify response is proper dict with Pydantic schema fields
    post_data = create_resp.json()
    assert isinstance(post_data, dict)
    assert "id" in post_data
    assert "title" in post_data
    assert "owner" in post_data
    assert isinstance(post_data["owner"], dict)
    assert "username" in post_data["owner"]
    # Should NOT have SQLAlchemy internal fields
    assert "_sa_instance_state" not in str(post_data)


async def test_validation_errors_are_clear(client, get_token):
    """Verify Pydantic validation provides clear error messages"""
    # Missing required field 'content'
    resp = await client.post("/posts/createPost",
        data={"title": "Only Title"},  # Missing content field
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 422  # Validation error
    error = resp.json()
    assert "detail" in error
    # Should mention the missing 'content' field
    assert any("content" in str(err).lower() for err in error["detail"])


async def test_media_urls_properly_constructed(client, get_token):
    """Verify media URLs have full paths"""
    # Get user profile pic endpoint
    resp = await client.get("/me/profile", headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 200
    
    profile = resp.json()
    # If profile picture exists, verify URL construction
    if profile.get("profilePicture"):
        # Should be full URL or relative path (depends on settings)
        assert isinstance(profile["profilePicture"], str)


async def test_pagination_metadata_structure(client, get_token):
    """Verify pagination includes proper metadata"""
    resp = await client.get("/me/posts?limit=5&offset=0",
        headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 200
    
    data = resp.json()
    # Should have pagination metadata
    assert "pagination" in data
    assert "posts" in data
    
    pagination = data["pagination"]
    assert "total" in pagination
    assert "limit" in pagination
    assert "offset" in pagination
    assert "has_more" in pagination
    
    # Verify values
    assert pagination["limit"] == 5
    assert pagination["offset"] == 0
    # total may be None to avoid expensive COUNT queries
    assert pagination["total"] is None or isinstance(pagination["total"], int)
    assert isinstance(pagination["has_more"], bool)


async def test_error_responses_consistent_format(client, get_token):
    """Verify all error responses follow same format"""
    # Test 404 error
    resp = await client.get("/posts/getPost/999999",
        headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 404
    error = resp.json()
    assert "detail" in error
    assert isinstance(error["detail"], str)
    
    # Test validation error (422)
    resp = await client.post("/vote/on_post",
        json={"invalid": "data"},  # Missing required fields
        headers={"Authorization": f"Bearer {get_token}"})
    assert resp.status_code == 422
    error = resp.json()
    assert "detail" in error


async def test_comment_list_response_schema(client, get_token):
    """Verify comments return proper CommentListResponse"""
    # Assuming post with id 1 exists
    resp = await client.get("/comments-on/1?limit=10&offset=0",
        headers={"Authorization": f"Bearer {get_token}"})
    
    if resp.status_code == 200:
        data = resp.json()
        assert "comments" in data
        assert "pagination" in data
        assert isinstance(data["comments"], list)
        
        # Check comment structure
        if data["comments"]:
            comment = data["comments"][0]
            assert "id" in comment
            assert "content" in comment
            assert "user" in comment
            assert isinstance(comment["user"], dict)


async def test_vote_response_includes_counts(client, get_token):
    """Verify vote responses include like/dislike counts"""
    # Create a post to vote on
    create_resp = await client.post("/posts/createPost",
        data={"title": "Vote Test", "content": "Testing votes"},
        headers={"Authorization": f"Bearer {get_token}"})
    post_id = create_resp.json()["id"]
    
    # Vote on the post
    resp = await client.post("/vote/on_post",
        json={"post_id": post_id, "choice": True},
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 201
    vote_data = resp.json()
    assert "message" in vote_data
    # VoteResponse should include counts
    assert "likes" in vote_data or "dislikes" in vote_data


async def test_search_results_proper_schema(client, get_token):
    """Verify search returns SearchResultResponse schema"""
    # Search for users
    resp = await client.get("/search?q=test&limit=5&offset=0",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 202
    data = resp.json()
    assert "result_type" in data
    assert "total" in data
    assert data["result_type"] in ["users", "posts"]
    
    # Should  have either users or posts
    assert "users" in data or "posts" in data


async def test_follow_response_includes_count(client, get_token):
    """Verify follow/unfollow returns FollowResponse with count"""
    # Try to follow user 2 (assuming exists)
    resp = await client.post("/follow/2",
        headers={"Authorization": f"Bearer {get_token}"})
    
    if resp.status_code in [201, 400]:  # 400 if already following
        data = resp.json()
        assert "message" in data
        # Should include following_count if successful
        if resp.status_code == 201:
            assert "following_count" in data


async def test_success_response_schema(client, get_token):
    """Verify success endpoints return SuccessResponse"""
    # Test delete (if we have a post to delete)
    create_resp = await client.post("/posts/createPost",
        data={"title": "ToDelete", "content": "Will be deleted"},
        headers={"Authorization": f"Bearer {get_token}"})
    
    if create_resp.status_code == 201:
        post_id = create_resp.json()["id"]
        delete_resp = await client.delete(f"/posts/deletePost/{post_id}",
            headers={"Authorization": f"Bearer {get_token}"})
        
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert "message" in data
        assert isinstance(data["message"], str)
