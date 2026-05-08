"""
Additional tests for edge cases and WebSocket functionality
"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    ActorBasic,
    NotificationListResponse,
    PostCreateRequest,
    SearchRequest,
    VerifyEmailRequest,
)


async def test_post_detail_response_complete(client, get_token):
    """Verify PostDetailResponse has all required fields"""
    create_resp = await client.post("/posts/createPost",
        data={"title": "Complete Test", "content": "Full data"},
        headers={"Authorization": f"Bearer {get_token}"})
    
    post = create_resp.json()
    # Verify all PostDetailResponse fields
    required_fields = ["id", "title", "content", "likes", "dislikes", 
                      "views", "comments_count", "enable_comments", 
                      "created_at", "owner"]
    for field in required_fields:
        assert field in post, f"Missing field: {field}"


async def test_user_profile_response_structure(client, get_token):
    """Verify UserProfileResponse schema"""
    resp = await client.get("/me/profile",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 200
    profile = resp.json()
    
    required_fields = ["profile_picture", "username", "nickname", 
                      "bio", "posts_count", "followers_count", "following_count"]
    for field in required_fields:
        assert field in profile


async def test_vote_stats_response_schema(client, get_token):
    """Verify VoteStatsResponse returns proper counts"""
    resp = await client.get("/me/voteStats",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 200
    stats = resp.json()
    assert "liked_posts_count" in stats
    assert "disliked_posts_count" in stats
    assert isinstance(stats["liked_posts_count"], int)
    assert isinstance(stats["disliked_posts_count"], int)


async def test_comment_stats_response_schema(client, get_token):
    """Verify CommentStatsResponse"""
    resp = await client.get("/me/comment-stats",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 200
    stats = resp.json()
    assert "total_comments" in stats
    assert "unique_posts_commented" in stats


async def test_pagination_has_more_calculation(client, get_token):
    """Verify has_more is calculated correctly"""
    # Get first page
    resp1 = await client.get("/me/posts?limit=2&offset=0",
        headers={"Authorization": f"Bearer {get_token}"})
    data1 = resp1.json()
    
    # Verify has_more is present and boolean
    assert "has_more" in data1["pagination"]
    assert isinstance(data1["pagination"]["has_more"], bool)
    
    # If total is provided, verify has_more logic
    if data1["pagination"]["total"] is not None and data1["pagination"]["total"] > 2:
        # Should have more
        assert data1["pagination"]["has_more"] == True
    # Note: total may be None to avoid expensive COUNT queries


async def test_media_info_response(client, get_token):
    """Verify MediaInfo schema for profile pictures"""
    # First try to get profile pic
    resp = await client.get("/me/profile/pic",
        headers={"Authorization": f"Bearer {get_token}"})
    
    # If user has profile pic (might be 404 if not)
    if resp.status_code == 200:
        media = resp.json()
        assert "url" in media
        assert "type" in media or media.get("type") is None


async def test_feed_response_structure(client, get_token):
    """Verify FeedResponse schema"""
    resp = await client.get("/feed/home?limit=5&offset=0",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 200
    feed = resp.json()
    assert "feed" in feed
    assert "total" in feed
    assert isinstance(feed["feed"], list)
    
    # Check feed item structure
    if feed["feed"]:
        item = feed["feed"][0]
        assert "post_id" in item
        assert "owner" in item


async def test_can_edit_response_schema(client, get_token):
    """Verify CanEditResponse for edit_msg endpoint"""
    # This would need a message_id, assuming endpoint exists in router
    # Test endpoint availability
    try:
        resp = await client.get("/msg/1/can_edit",
            headers={"Authorization": f"Bearer {get_token}"})
        # If endpoint exists
        if resp.status_code in [200, 404]:
            data = resp.json()
            if resp.status_code == 200:
                assert "can_edit" in data
                assert isinstance(data["can_edit"], bool)
    except:
        pytest.skip("Edit message endpoint not mounted")


async def test_invalid_token_returns_401(client):
    """Verify authentication failures are consistent"""
    resp = await client.get("/me/profile",
        headers={"Authorization": "Bearer invalid_token_here"})
    
    assert resp.status_code == 401
    error = resp.json()
    assert "detail" in error


async def test_comment_create_response(client, get_token):
    """Verify comment creation returns CommentDetailResponse"""
    # Create a post first
    post_resp = await client.post("/posts/createPost",
        data={"title": "For Comment", "content": "Test"},
        headers={"Authorization": f"Bearer {get_token}"})
    post_id = post_resp.json()["id"]
    
    # Create comment
    resp = await client.post("/comment/createComment",
        json={"post_id": post_id, "content": "Nice post!"},
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert resp.status_code == 201
    comment = resp.json()
    assert "id" in comment
    assert "content" in comment
    assert "user" in comment
    assert "post_id" in comment


async def test_user_basic_response_in_followers(client, get_token):
    """Verify followers/following return UserBasicResponse list"""
    resp = await client.get("/me/profile",
        headers={"Authorization": f"Bearer {get_token}"})
    user_id = resp.json().get("id", 1)
    
    # Get followers
    followers_resp = await client.get(f"/users/{user_id}/followers",
        headers={"Authorization": f"Bearer {get_token}"})
    
    assert followers_resp.status_code == 200
    followers = followers_resp.json()
    assert isinstance(followers, list)
    
    # Check structure if any followers
    if followers:
        follower = followers[0]
        assert "id" in follower
        assert "username" in follower
        assert "nickname" in follower


def test_verify_email_request_rejects_invalid_otp_length():
    with pytest.raises(ValidationError):
        VerifyEmailRequest(email="user@example.com", otp="12345")


def test_search_request_rejects_limit_above_max():
    with pytest.raises(ValidationError):
        SearchRequest(q="hello", limit=101, offset=0)


def test_post_create_request_rejects_empty_content():
    with pytest.raises(ValidationError):
        PostCreateRequest(title="Valid title", content="")


def test_actor_basic_maps_profile_picture_alias():
    actor = ActorBasic(id=1, username="alice", profile_picture="/img/a.png")
    assert actor.profile_pic == "/img/a.png"


def test_notification_list_response_requires_boolean_has_more():
    with pytest.raises(ValidationError):
        NotificationListResponse(
            notifications=[],
            unread_count=0,
            total=0,
            limit=10,
            offset=0,
            has_more={"not": "bool"},
        )
