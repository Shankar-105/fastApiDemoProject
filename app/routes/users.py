from fastapi import status,HTTPException,Depends,Body,APIRouter,Query
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func
from app.utils import thread_helpers as utils
import os
import logging
from app.services.redis_service import get_cache, set_cache, delete_cache, delete_cache_pattern
from app.services.rate_limit_service import signup_limiter
from app.services.blob_service import get_blob_url
import app.services.otp_service as otp_service
import app.services.email_service as email_service
from app.tasks.email_tasks import send_verification_email as send_verification_email_task
router=APIRouter(
    prefix="/users",
    tags=['Users']
)

logger = logging.getLogger("app")

@router.get("/{user_id}", status_code=status.HTTP_200_OK, response_model=sch.UserProfileResponse)
async def get_user_profile(user_id:int, db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching profile for user_id: {user_id}, requested by: {currentUser.id}")
    cache_key = f"user_profile:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        is_following_query = await db.execute(
            select(
                select(models.connections.c.followed_id)
                .where(
                    models.connections.c.follower_id == currentUser.id,
                    models.connections.c.followed_id == user_id,
                )
                .exists()
            )
        )
        cached["is_following"] = bool(is_following_query.scalar())
        logger.info(f"User profile {user_id} retrieved from cache for user: {currentUser.id}")
        return cached

    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        logger.warning(f"User profile not found: {user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    
    is_following_query = await db.execute(
        select(
            select(models.connections.c.followed_id)
            .where(
                models.connections.c.follower_id == currentUser.id,
                models.connections.c.followed_id == user_id,
            )
            .exists()
        )
    )
    is_following = bool(is_following_query.scalar())
    
    posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==user_id))
    posts_count = posts_count_result.scalar()
    
    result_response = sch.UserProfileResponse(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        bio=user.bio or "",
        profile_picture=user.profile_picture,
        posts_count=posts_count,
        followers_count=user.followers_cnt,
        following_count=user.following_cnt,
        is_following=is_following,
        created_at=user.created_at
    )

    await set_cache(cache_key, result_response.model_dump(mode="json"), ttl=120)
    logger.info(f"User profile {user_id} retrieved from DB for user: {currentUser.id}")
    return result_response

@router.get("/{user_id}/avatar", status_code=status.HTTP_200_OK, response_model=sch.MediaInfo)
async def get_user_avatar(user_id:int, db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching avatar for user_id: {user_id}")
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    profilePicturePath = user.profile_picture
    if not profilePicturePath:
        logger.warning(f"No profile picture for user_id: {user_id}")
        raise HTTPException(status_code=404, detail="No profile picture")
    logger.info(f"Avatar retrieved for user_id: {user_id}")
    return sch.MediaInfo(
        url=get_blob_url("profilepics", profilePicturePath),
        type="image"
    )

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=sch.UserResponse)
async def register_user(userData:sch.UserSignupRequest=Body(...), db:AsyncSession=Depends(db.getDb), _:None=Depends(signup_limiter)):
    logger.info(f"Registration attempt for username: {userData.username}, email: {userData.email}")
    existing_email = await db.execute(select(models.User).where(models.User.email == userData.email))
    if existing_email.scalars().first():
        logger.warning(f"Registration failed - email already exists: {userData.email}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    hashedPw=await utils.hashPassword(userData.password)
    userData.password=hashedPw
    user_payload = userData.model_dump()
    user_payload["email_verified"] = False
    newUser=models.User(**user_payload)
    db.add(newUser)
    await db.commit()
    await db.refresh(newUser)

    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, userData.email, otp, minutes=5)
    
    send_verification_email_task.delay(to_email=userData.email, otp=otp)

    await delete_cache("all_users")
    logger.info(f"User registered successfully: {newUser.username}, id: {newUser.id}")
    return newUser

@router.get("", status_code=status.HTTP_200_OK, response_model=List[sch.UserResponse])
async def list_users(db:AsyncSession=Depends(db.getDb)):
    logger.debug("Listing all users")
    cached = await get_cache("all_users")
    if cached:
        logger.info("Users list retrieved from cache")
        return cached

    result=await db.execute(
        select(models.User.id, models.User.username, models.User.created_at)
    )
    rows=result.all()

    users_data = [
        sch.UserResponse(id=row.id, username=row.username, created_at=row.created_at).model_dump(mode="json")
        for row in rows
    ]
    await set_cache("all_users", users_data, ttl=60)
    logger.info(f"Users list retrieved from DB, count: {len(users_data)}")
    return [sch.UserResponse(**item) for item in users_data]

@router.get("/{user_id}/followers", status_code=status.HTTP_200_OK, response_model=List[sch.UserBasicResponse])
async def get_followers(user_id:int, db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching followers for user_id: {user_id}")
    cache_key = f"followers:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"Followers for user_id: {user_id} retrieved from cache")
        return cached

    follower_link = models.connections.alias("follower_link")
    result=await db.execute(
        select(models.User)
        .join(follower_link, follower_link.c.follower_id == models.User.id)
        .where(follower_link.c.followed_id == user_id)
    )
    followers=result.scalars().all()
    if not followers:
        exists_result=await db.execute(select(models.User.id).where(models.User.id == user_id))
        if not exists_result.first():
            logger.warning(f"User not found when fetching followers: {user_id}")
            raise HTTPException(status_code=404,detail="User not found")
    followers_response = []
    for follower in followers:
        followers_response.append(sch.UserBasicResponse(
            id=follower.id,
            username=follower.username,
            nickname=follower.nickname,
            profile_pic=follower.profile_picture
        ))
    await set_cache(cache_key, [f.model_dump(mode="json") for f in followers_response], ttl=120)
    logger.info(f"Followers for user_id: {user_id} retrieved from DB, count: {len(followers_response)}")
    return followers_response

@router.get("/{user_id}/following", status_code=status.HTTP_200_OK, response_model=List[sch.UserBasicResponse])
async def get_following(user_id:int, db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching following for user_id: {user_id}")
    cache_key = f"following:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"Following for user_id: {user_id} retrieved from cache")
        return cached

    following_link = models.connections.alias("following_link")
    result=await db.execute(
        select(models.User)
        .join(following_link, following_link.c.followed_id == models.User.id)
        .where(following_link.c.follower_id == user_id)
    )
    following=result.scalars().all()
    if not following:
        exists_result=await db.execute(select(models.User.id).where(models.User.id == user_id))
        if not exists_result.first():
            logger.warning(f"User not found when fetching following: {user_id}")
            raise HTTPException(status_code=404,detail="User not found")
    following_response = []
    for followed_user in following:
        following_response.append(sch.UserBasicResponse(
            id=followed_user.id,
            username=followed_user.username,
            nickname=followed_user.nickname,
            profile_pic=followed_user.profile_picture
        ))
    await set_cache(cache_key, [f.model_dump(mode="json") for f in following_response], ttl=120)
    logger.info(f"Following for user_id: {user_id} retrieved from DB, count: {len(following_response)}")
    return following_response

@router.get("/{user_id}/posts", response_model=sch.PostListResponse)
async def get_user_posts(user_id:int, limit:int=Query(10, ge=1, le=100), offset: int = Query(0, ge=0), db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching posts for user_id: {user_id}, limit: {limit}, offset: {offset}")
    cache_key = f"user:posts:{user_id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"Posts for user_id: {user_id} retrieved from cache")
        return cached

    is_liked = (
        select(models.Votes.post_id)
        .where(
            models.Votes.user_id == currentUser.id,
            models.Votes.post_id == models.Post.id,
            models.Votes.action == True,
        )
        .exists()
        .label("is_liked")
    )
    postsResult=await db.execute(
        select(models.Post, is_liked)
        .where(models.Post.user_id==user_id)
        .order_by(models.Post.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    paginatedPosts=postsResult.all()
    has_more = len(paginatedPosts) > limit
    paginatedPosts = paginatedPosts[:limit]

    posts = []
    for post, liked in paginatedPosts:
        media_url = None
        if post.media_path:
            media_url = get_blob_url("posts-media", post.media_path)
        posts.append(sch.PostListItemResponse(
            id=post.id,
            title=post.title,
            media_url=media_url,
            media_type=post.media_type,
            likes=post.likes,
            comments_count=post.comments_cnt,
            is_liked=bool(liked),
            created_at=post.created_at
        ))
    
    pagination = sch.PaginationMetadata(
        total=None,
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    result = sch.PostListResponse(
        posts=posts,
        pagination=pagination
    )
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=60)
    logger.info(f"Posts for user_id: {user_id} retrieved from DB, count: {len(posts)}")
    return result
