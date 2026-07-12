from fastapi import status,HTTPException,Depends,APIRouter,Form,UploadFile,File
import app.schemas as sch
from app.services.rate_limit_service import create_post_limiter
from app.services.idempotency_service import get_idempotency_key, idempotent
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
import structlog
from app.config import settings
from app.services.blob_service import upload_blob, delete_blob, get_blob_url
from app.utils.exceptions import ResourceNotFoundException, ValidationException

router=APIRouter(
    prefix="/posts",
    tags=['Posts']
)

logger = structlog.get_logger(__name__)

# gets a specific post with id -> {postId}
@router.get("/{postId}", response_model=sch.PostDetailResponse)
async def get_post(postId:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug("fetching_post", post_id=postId, user_id=currentUser.id)
    cache_key = f"post:{postId}:{currentUser.id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("post_cache_hit", post_id=postId, user_id=currentUser.id)
        return cached

    result=await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.user))
        .where(models.Post.id==postId)
    )
    reqPost=result.scalars().first()
    if reqPost==None:
        logger.warning("post_not_found", post_id=postId)
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    
    await queue_post_view(postId, currentUser.id)
    
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
    logger.info("post_retrieved_db", post_id=postId, user_id=currentUser.id)
    return result_response


# creates a new post using sqlAlchemy
@router.post("", status_code=status.HTTP_201_CREATED, response_model=sch.PostDetailResponse)
@idempotent(endpoint_identifier="create_post")
async def create_post(
    title:str=Form(...),
    content:str=Form(...),
    media:Optional[UploadFile]=File(None),  # Optional file
    db: AsyncSession=Depends(getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    _:None=Depends(create_post_limiter),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("create_post_attempt", user_id=currentUser.id)
    media_path = None
    media_type = None
    if media:
        if media.content_type not in ["image/jpeg", "image/png", "video/mp4"]:
            logger.warning("create_post_invalid_media", user_id=currentUser.id, content_type=media.content_type)
            raise ValidationException("Only JPG, PNG, MP4 allowed")
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
    
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    
    await delete_cache_pattern(f"user:posts:{currentUser.id}:*")
    
    media_url = None
    if new_post.media_path:
        media_url = get_blob_url("posts-media", new_post.media_path)
    
    owner = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    logger.info("create_post_success", user_id=currentUser.id, post_id=new_post.id)
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
@idempotent(endpoint_identifier="delete_post")
async def delete_post(
    postId:int, 
    db:AsyncSession=Depends(getDb), 
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("delete_post_attempt", user_id=currentUser.id, post_id=postId)
    result=await db.execute(select(models.Post).where(and_(models.Post.id==postId,models.Post.user_id==currentUser.id)))
    postToDelete=result.scalars().first()
    if not postToDelete:
        logger.warning("delete_post_failed", user_id=currentUser.id, post_id=postId, reason="not_found_or_unauthorized")
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    if postToDelete.media_path:
        await delete_blob("posts-media", postToDelete.media_path)
    await db.delete(postToDelete)
    await db.commit()
    await delete_cache_pattern(f"post:{postId}:*")
    
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    await delete_cache_pattern(f"user:posts:{currentUser.id}:*")
    await delete_cache_pattern(f"comments:post:{postId}:*")
    logger.info("delete_post_success", user_id=currentUser.id, post_id=postId)
    return sch.SuccessResponse(message=f"Post {postToDelete.id} deleted successfully")

# update a specific post with id -> {id}
@router.put("/{postId}", response_model=sch.PostDetailResponse)
@idempotent(endpoint_identifier="update_post")
async def update_post(
    postId:int, 
    post:sch.PostUpdateRequest, 
    db:AsyncSession=Depends(getDb), 
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("update_post_attempt", user_id=currentUser.id, post_id=postId)
    result=await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.user))
        .where(models.Post.id==postId)
    )
    postToUpdate=result.scalars().first()
    if not postToUpdate:
        logger.warning("update_post_failed", user_id=currentUser.id, post_id=postId, reason="not_found")
        raise ResourceNotFoundException(resource="Post", identifier=postId)
    update_data = post.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(postToUpdate,key,value)
    await db.commit()
    await delete_cache_pattern(f"post:{postId}:*")
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    
    media_url = None
    if postToUpdate.media_path:
        media_url = get_blob_url("posts-media", postToUpdate.media_path)
    
    owner = sch.UserBasicResponse(
        id=postToUpdate.user.id,
        username=postToUpdate.user.username,
        nickname=postToUpdate.user.nickname,
        profile_pic=postToUpdate.user.profile_picture
    )
    
    logger.info("update_post_success", user_id=currentUser.id, post_id=postId)
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
