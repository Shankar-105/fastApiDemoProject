from fastapi import status,HTTPException,Depends,APIRouter,Form,UploadFile,File
import app.schemas as sch
from app.rate_limiter import create_post_limiter
from typing import Optional
from app import models,oauth2
from app.db import getDb
from app.services.redis_service import get_cache, set_cache, delete_cache, delete_cache_pattern, queue_post_view, increment_cache_version, get_cache_version, build_versioned_feed_cache_key
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
import os,uuid
import asyncio
from app.config import settings
from app.services.blob_service import upload_blob, delete_blob, get_blob_url
router=APIRouter(
    prefix="/posts",
    tags=['Posts']
)

from app.utils.exceptions import ResourceNotFoundException, ValidationException

# gets a specific post with id -> {postId}
@router.get("/{postId}", response_model=sch.PostDetailResponse)
async def get_post(postId:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Check Redis cache first
    cache_key = f"post:{postId}:{currentUser.id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    result=await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.user))
        .where(models.Post.id==postId)
    )
    reqPost=result.scalars().first()
    if reqPost==None:
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    
    # ... rest of the function ...
    await queue_post_view(postId, currentUser.id)
    
    # Check if liked
    likeResult=await db.execute(
        select(
            select(models.Votes.post_id)
            .where(
                models.Votes.post_id == postId,
                models.Votes.user_id == currentUser.id,
                models.Votes.action == True,
            )
            .exists()
        )
    )
    is_liked = bool(likeResult.scalar())
    
    # Build proper response with schema
    media_url = None
    if reqPost.media_path:
        media_url = get_blob_url("posts-media", reqPost.media_path)
    
    owner = sch.UserBasicResponse(
        id=reqPost.user.id,
        username=reqPost.user.username,
        nickname=reqPost.user.nickname,
        profile_pic=reqPost.user.profile_picture
    )
    
    result_response = sch.PostDetailResponse(
        id=reqPost.id,
        title=reqPost.title,
        content=reqPost.content,
        media_url=media_url,
        media_type=reqPost.media_type,
        likes=reqPost.likes,
        dislikes=reqPost.dis_likes,
        views=reqPost.views,
        comments_count=reqPost.comments_cnt,
        enable_comments=reqPost.enable_comments,
        hashtags=reqPost.hashtags,
        created_at=reqPost.created_at,
        is_liked=is_liked,
        owner=owner
    )
    await set_cache(cache_key, result_response.model_dump(mode="json"), ttl=120)
    return result_response


# creates a new post using sqlAlchemy
@router.post("", status_code=status.HTTP_201_CREATED, response_model=sch.PostDetailResponse)
async def create_post(
    title:str=Form(...),
    content:str=Form(...),
    media:Optional[UploadFile]=File(None),  # Optional file
    db: AsyncSession=Depends(getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    _:None=Depends(create_post_limiter),
):
    # set to None change if uploaded later
    media_path = None
    media_type = None
    if media:
        # ensure the file type is in bounds
        if media.content_type not in ["image/jpeg", "image/png", "video/mp4"]:
            raise ValidationException("Only JPG, PNG, MP4 allowed")
        # Generate unique filename
        # using uuid Universally unique ID which generates a 36 characters
        ext=media.filename.split(".")[-1]
        filename=f"{uuid.uuid4()}.{ext}"
        content_bytes = await media.read()
        await upload_blob("posts-media", filename, content_bytes, media.content_type)
        media_path=filename
        media_type="image" if media.content_type.startswith("image") else "video"
    new_post = models.Post(
        title=title,
        content=content,
        media_path=media_path,
        media_type=media_type,
        user_id=currentUser.id
    )
    db.add(new_post)
    await db.commit()
    
    # Use versioned cache keys instead of global feed:* invalidation (always enabled).
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    
    await delete_cache_pattern(f"user:posts:{currentUser.id}:*")
    
    # Build proper response (no refresh needed)
    media_url = None
    if new_post.media_path:
        media_url = get_blob_url("posts-media", new_post.media_path)
    
    owner = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    return sch.PostDetailResponse(
        id=new_post.id,
        title=new_post.title,
        content=new_post.content,
        media_url=media_url,
        media_type=new_post.media_type,
        likes=new_post.likes,
        dislikes=new_post.dis_likes,
        views=new_post.views,
        comments_count=new_post.comments_cnt,
        enable_comments=new_post.enable_comments,
        hashtags=new_post.hashtags,
        created_at=new_post.created_at,
        owner=owner
    )
# delets a specific post with the mentioned id -> {id}
@router.delete("/{postId}", response_model=sch.SuccessResponse)
async def delete_post(postId:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.Post).where(and_(models.Post.id==postId,models.Post.user_id==currentUser.id)))
    postToDelete=result.scalars().first()
    if not postToDelete:
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    # Fix bug: construct path before checking existence
    if postToDelete.media_path:
        await delete_blob("posts-media", postToDelete.media_path)
    await db.delete(postToDelete)
    await db.commit()
    # Invalidate caches for this post, feeds, and user posts
    await delete_cache_pattern(f"post:{postId}:*")
    
    # Use versioned cache keys instead of global feed:* invalidation (always enabled).
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    await delete_cache_pattern(f"user:posts:{currentUser.id}:*")
    await delete_cache_pattern(f"comments:post:{postId}:*")
    return sch.SuccessResponse(message=f"Post {postToDelete.id} deleted successfully")

# update a specific post with id -> {id}
@router.put("/{postId}", response_model=sch.PostDetailResponse)
async def update_post(postId:int, post:sch.PostUpdateRequest, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    result=await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.user))
        .where(models.Post.id==postId)
    )
    postToUpdate=result.scalars().first()
    if not postToUpdate:
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    # from our argument of post we exclude the None values
    # and just pick up the set values and store into a dict update_data
    update_data = post.dict(exclude_unset=True)
    # now we traverse thorugh the update_data and put that data
    # in our postToUpdate
    for key, value in update_data.items():
        setattr(postToUpdate,key,value)
    # commit those updated changes
    await db.commit()
    # No refresh needed - object has updated values and expire_on_commit=False keeps them
    # Invalidate cached post data and feeds
    await delete_cache_pattern(f"post:{postId}:*")
    # Use versioned cache keys instead of global feed:* invalidation (always enabled).
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    
    # Build proper response
    media_url = None
    if postToUpdate.media_path:
        media_url = get_blob_url("posts-media", postToUpdate.media_path)
    
    owner = sch.UserBasicResponse(
        id=postToUpdate.user.id,
        username=postToUpdate.user.username,
        nickname=postToUpdate.user.nickname,
        profile_pic=postToUpdate.user.profile_picture
    )
    
    return sch.PostDetailResponse(
        id=postToUpdate.id,
        title=postToUpdate.title,
        content=postToUpdate.content,
        media_url=media_url,
        media_type=postToUpdate.media_type,
        likes=postToUpdate.likes,
        dislikes=postToUpdate.dis_likes,
        views=postToUpdate.views,
        comments_count=postToUpdate.comments_cnt,
        enable_comments=postToUpdate.enable_comments,
        hashtags=postToUpdate.hashtags,
        created_at=postToUpdate.created_at,
        owner=owner
    )
