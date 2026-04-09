from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func,desc
from typing import List
from app import models, schemas, oauth2 , db
from app.services.redis_service import get_cache, set_cache, delete_cache
from app.services.blob_service import get_blob_url
import os

router = APIRouter(tags=["Feed"])

@router.get("/feed/home", response_model=schemas.FeedResponse)
async def getHomeFeed(limit:int=Query(10, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    # Check Redis cache first (per-user, per-page)
    cache_key = f"feed:home:{currentUser.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # Get users the current user follows via connections table
    followingResult = await db.execute(
        select(models.connections.c.followed_id).where(models.connections.c.follower_id == currentUser.id)
    )
    followed_users = [row[0] for row in followingResult.all()]
    
    # Query posts from followed users, recent first
    countResult = await db.execute(
        select(func.count()).select_from(models.Post).where(models.Post.user_id.in_(followed_users))
    )
    total=countResult.scalar()
    
    postsResult = await db.execute(
        select(models.Post).where(models.Post.user_id.in_(followed_users))
        .order_by(models.Post.created_at.desc())
        .offset(offset).limit(limit)
    )
    posts=postsResult.scalars().all()
    
    # Get liked post IDs
    votesResult = await db.execute(
        select(models.Votes.post_id).where(models.Votes.user_id == currentUser.id, models.Votes.action == True)
    )
    liked_post_ids = {row[0] for row in votesResult.all()}
    
    # Build proper feed response
    user_homeFeed = []
    for post in posts:
        owner = schemas.UserOut(
            id=post.user_id,
            username=post.user.username,
            profile_pic=post.user.profile_picture
        )
        # Build the post item with is_liked
        post_item = schemas.PostListItemResponse(
            id=post.id,
            title=post.title,
            media_url=get_blob_url("posts-media", post.media_path) if post.media_path else None,
            media_type=post.media_type,
            likes=post.likes,
            comments_count=post.comments_cnt,
            created_at=post.created_at,
            is_liked=post.id in liked_post_ids
        )
        
        user_homeFeed.append(schemas.FeedItemResponse(
            post_id=post.id,
            post=post_item,
            owner=owner
        ))
    
    result = schemas.FeedResponse(feed=user_homeFeed, total=total)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=30)
    return result

@router.get("/feed/explore", response_model=schemas.PostListResponse)
async def getExploreFeed(limit:int=Query(20, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    # Check Redis cache (per-user because is_liked differs per user)
    cache_key = f"feed:explore:{currentUser.id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # For explore, get all posts (or random) - excluding potentially private ones if that existed
    # Simple implementation: All recent posts
    countResult = await db.execute(select(func.count()).select_from(models.Post))
    total = countResult.scalar()
    
    postsResult = await db.execute(
        select(models.Post).order_by(models.Post.created_at.desc())
        .offset(offset).limit(limit)
    )
    posts = postsResult.scalars().all()
    
    # Get liked post IDs
    votesResult = await db.execute(
        select(models.Votes.post_id).where(models.Votes.user_id == currentUser.id, models.Votes.action == True)
    )
    liked_post_ids = {row[0] for row in votesResult.all()}
    
    # helper to format posts specifically for explore (similar to user posts list)
    explore_posts = []
    for post in posts:
        media_url = None
        if post.media_path:
            media_url = get_blob_url("posts-media", post.media_path)
            
        explore_posts.append(schemas.PostListItemResponse(
            id=post.id,
            title=post.title,
            media_url=media_url,
            media_type=post.media_type,
            likes=post.likes,
            comments_count=post.comments_cnt,
            created_at=post.created_at,
            is_liked=post.id in liked_post_ids
        ))

    pagination = schemas.PaginationMetadata(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(limit+offset)<total
    )
    
    result = schemas.PostListResponse(posts=explore_posts, pagination=pagination)
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=60)
    return result
