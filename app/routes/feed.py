from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func
from typing import List
from app import models, schemas, oauth2 , db
from app.services.redis_service import get_cache, set_cache, delete_cache
from app.services.blob_service import get_blob_url
import os
import structlog

router = APIRouter(
    prefix="/feed",
    tags=["Feed"]
)

logger = structlog.get_logger(__name__)

@router.get("", response_model=schemas.FeedResponse)
async def getHomeFeed(limit:int=Query(10, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    """Return posts from users the current user follows, newest first.

    Cached per ``feed:home:{user.id}:{offset}:{limit}`` for 30 seconds.
    Cache is versioned — ``increment_cache_version("feed:home")`` bumps
    the key so all home feeds refresh after new posts or follows.
    """
    logger.debug("fetching_home_feed", user_id=currentUser.id, limit=limit, offset=offset)
    cache_key = f"feed:home:{currentUser.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("home_feed_cache_hit", user_id=currentUser.id)
        return cached

    followed_users = (
        select(models.connections.c.followed_id)
        .where(models.connections.c.follower_id == currentUser.id)
    )
    is_liked = (
        select(models.Votes.post_id)
        .where(
            models.Votes.post_id == models.Post.id,
            models.Votes.user_id == currentUser.id,
            models.Votes.action == True,
        )
        .exists()
        .label("is_liked")
    )
    
    postsResult = await db.execute(
        select(
            models.Post.id,
            models.Post.title,
            models.Post.media_path,
            models.Post.media_type,
            models.Post.likes,
            models.Post.comments_cnt,
            models.Post.created_at,
            models.Post.user_id,
            models.User.username,
            models.User.profile_picture,
            is_liked,
        )
        .join(models.User, models.User.id == models.Post.user_id)
        .where(models.Post.user_id.in_(followed_users))
        .order_by(models.Post.created_at.desc())
        .offset(offset).limit(limit + 1)
    )
    rows=postsResult.all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    
    user_homeFeed = []
    for row in rows:
        owner = schemas.UserOut(
            id=row.user_id,
            username=row.username,
            profile_pic=row.profile_picture
        )
        post_item = schemas.PostListItemResponse(
            id=row.id,
            title=row.title,
            media_url=get_blob_url("posts-media", row.media_path) if row.media_path else None,
            media_type=row.media_type,
            likes=row.likes,
            comments_count=row.comments_cnt,
            created_at=row.created_at,
            is_liked=bool(row.is_liked)
        )
        
        user_homeFeed.append(schemas.FeedItemResponse(
            post_id=row.id,
            post=post_item,
            owner=owner
        ))
    
    result = schemas.FeedResponse(feed=user_homeFeed, total=None)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=30)
    logger.info("home_feed_retrieved_db", user_id=currentUser.id, items_count=len(user_homeFeed))
    return result

@router.get("/explore", response_model=schemas.PostListResponse)
async def getExploreFeed(limit:int=Query(20, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    """Return recent posts from *all* users (discovery feed).

    Cached per ``feed:explore:{user.id}:{offset}:{limit}`` for 60
    seconds.  Unlike the home feed, this is not filtered by follow
    relationships — it is a global chronological timeline.
    """
    logger.debug("fetching_explore_feed", user_id=currentUser.id, limit=limit, offset=offset)
    cache_key = f"feed:explore:{currentUser.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("explore_feed_cache_hit", user_id=currentUser.id)
        return cached

    is_liked = (
        select(models.Votes.post_id)
        .where(
            models.Votes.post_id == models.Post.id,
            models.Votes.user_id == currentUser.id,
            models.Votes.action == True,
        )
        .exists()
        .label("is_liked")
    )
    postsResult = await db.execute(
        select(
            models.Post.id,
            models.Post.title,
            models.Post.media_path,
            models.Post.media_type,
            models.Post.likes,
            models.Post.comments_cnt,
            models.Post.created_at,
            is_liked
        ).order_by(models.Post.created_at.desc())
        .offset(offset).limit(limit + 1)
    )
    rows = postsResult.all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    
    explore_posts = []
    for row in rows:
        media_url = None
        if row.media_path:
            media_url = get_blob_url("posts-media", row.media_path)
            
        explore_posts.append(schemas.PostListItemResponse(
            id=row.id,
            title=row.title,
            media_url=media_url,
            media_type=row.media_type,
            likes=row.likes,
            comments_count=row.comments_cnt,
            created_at=row.created_at,
            is_liked=bool(row.is_liked)
        ))

    pagination = schemas.PaginationMetadata(
        total=None,
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    result = schemas.PostListResponse(posts=explore_posts, pagination=pagination)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=60)
    logger.info("explore_feed_retrieved_db", user_id=currentUser.id, items_count=len(explore_posts))
    return result
