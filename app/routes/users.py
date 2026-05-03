from fastapi import status,HTTPException,Depends,Body,APIRouter,Query
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
import app.my_utils.utils as utils
import os
from app.services.redis_service import get_cache, set_cache, delete_cache, delete_cache_pattern
from app.rate_limiter import signup_limiter
from app.services.blob_service import get_blob_url
import app.services.otp_service as otp_service
import app.services.email_service as email_service
from app.tasks.email_tasks import send_verification_email as send_verification_email_task
router=APIRouter(
    tags=['Users']
)

@router.get("/users/{user_id}/profile",status_code=status.HTTP_200_OK,response_model=sch.UserProfileResponse)
async def userProfile(user_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Explicitly check if following
    is_following_query = await db.execute(
        select(models.connections).where(
            models.connections.c.follower_id == currentUser.id,
            models.connections.c.followed_id == user_id
        )
    )
    is_following = is_following_query.first() is not None

    # Check Redis cache first 
    cache_key = f"user_profile:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        # Cache HIT -> return the cached dict directly (FastAPI serializes it)
        cached["is_following"] = is_following
        return cached

    # Cache MISS -> query the database
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    
    # Count posts via query instead of len(user.posts) for efficiency
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

    #  Store in Redis for 120 seconds
    await set_cache(cache_key, result_response.model_dump(mode="json"), ttl=120)
    return result_response

@router.get("/users/{user_id}/profile/pic",status_code=status.HTTP_200_OK, response_model=sch.MediaInfo)
async def myProfilePicture(user_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # get the current users profile pic
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    profilePicturePath = user.profile_picture
    # if he doesnt have a porfile pic return 404
    if not profilePicturePath:
        raise HTTPException(status_code=404, detail="No profile picture")
    return sch.MediaInfo(
        url=get_blob_url("profilepics", profilePicturePath),
        type="image"
    )

@router.post("/user/signup",status_code=status.HTTP_201_CREATED,response_model=sch.UserResponse)
async def createUser(userData:sch.UserSignupRequest=Body(...),db:AsyncSession=Depends(db.getDb),_:None=Depends(signup_limiter)):
    # prevent duplicate emails to keep OTP verification deterministic per user
    existing_email = await db.execute(select(models.User).where(models.User.email == userData.email))
    if existing_email.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    # hash the password using the bcrypt lib (offloaded to thread pool)
    hashedPw=await utils.hashPassword(userData.password)
    userData.password=hashedPw
    user_payload = userData.model_dump()
    user_payload["email_verified"] = False
    newUser=models.User(**user_payload)
    db.add(newUser)
    await db.commit()
    await db.refresh(newUser)

    # send signup verification OTP
    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, userData.email, otp, minutes=5)
    
    send_verification_email_task.delay(to_email=userData.email, otp=otp)

    # Invalidate the all_users cache because a new user was added
    await delete_cache("all_users")
    return newUser

@router.get("/users/getAllUsers",status_code=status.HTTP_201_CREATED,response_model=List[sch.UserResponse])
async def getAllUsers(db:AsyncSession=Depends(db.getDb)):
    # Check the cache first
    cached = await get_cache("all_users")
    if cached:
        return cached   # cache HIT

    #  Cache MISS -> hit DB
    result=await db.execute(select(models.User))
    allUsers=result.scalars().all()

    # Build serializable list & cache it for 60 seconds
    users_data = [sch.UserResponse.model_validate(u).model_dump(mode="json") for u in allUsers]
    await set_cache("all_users", users_data, ttl=60)

    return allUsers

@router.get("/users/{user_id}/followers",status_code=status.HTTP_200_OK, response_model=List[sch.UserBasicResponse])
async def get_followers(user_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Check Redis cache
    cache_key = f"followers:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # explicit selectinload needed for self-referential many-to-many in async
    result=await db.execute(
        select(models.User)
        .where(models.User.id == user_id)
        .options(selectinload(models.User.followers))
    )
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    # Build proper response
    followers = []
    for follower in user.followers:
        followers.append(sch.UserBasicResponse(
            id=follower.id,
            username=follower.username,
            nickname=follower.nickname,
            profile_pic=follower.profile_picture
        ))
    await set_cache(cache_key, [f.model_dump(mode="json") for f in followers], ttl=120)
    return followers

@router.get("/users/{user_id}/following",status_code=status.HTTP_200_OK, response_model=List[sch.UserBasicResponse])
async def get_following(user_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Check Redis cache
    cache_key = f"following:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # explicit selectinload needed for self-referential many-to-many in async
    result=await db.execute(
        select(models.User)
        .where(models.User.id == user_id)
        .options(selectinload(models.User.following))
    )
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    # Build proper response
    following = []
    for followed_user in user.following:
        following.append(sch.UserBasicResponse(
            id=followed_user.id,
            username=followed_user.username,
            nickname=followed_user.nickname,
            profile_pic=followed_user.profile_picture
        ))
    await set_cache(cache_key, [f.model_dump(mode="json") for f in following], ttl=120)
    return following

@router.get("/users/{user_id}/posts", response_model=sch.PostListResponse)  
async def getAllPosts(user_id:int,limit:int=Query(10, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    # Check Redis cache
    cache_key = f"user:posts:{user_id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # calculate the total number of posts of the user
    countResult=await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==user_id))
    total=countResult.scalar()
    # only fetch the first 'limit' posts after skipping the first 'offset' posts
    # and order them by the latest as first
    postsResult=await db.execute(select(models.Post).where(models.Post.user_id==user_id).order_by(models.Post.created_at.desc()).offset(offset).limit(limit))
    paginatedPosts=postsResult.scalars().all()

    # Determine which posts the current user has liked
    liked_ids: set[int] = set()
    if paginatedPosts:
        post_ids = [p.id for p in paginatedPosts]
        liked_result = await db.execute(
            select(models.Votes.post_id)
            .where(models.Votes.user_id == currentUser.id, models.Votes.post_id.in_(post_ids), models.Votes.action == True)
        )
        liked_ids = {row[0] for row in liked_result.all()}

    # Build proper response
    posts = []
    for post in paginatedPosts:
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
            is_liked=post.id in liked_ids,
            created_at=post.created_at
        ))
    
    pagination = sch.PaginationMetadata(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(limit+offset)<total
    )
    
    result = sch.PostListResponse(
        posts=posts,
        pagination=pagination
    )
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=60)
    return result
