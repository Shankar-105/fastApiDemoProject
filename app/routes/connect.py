from fastapi import status,HTTPException,Depends,Body,APIRouter,BackgroundTasks
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,insert,delete,func
from sqlalchemy.exc import IntegrityError
from typing import List
from app.redis_service import delete_cache, delete_cache_pattern
from app.notification_service import create_notification
from app.models import NotificationType
from app.rate_limiter import follow_limiter

router=APIRouter(tags=['connections'])

@router.post("/follow/{user_id}",status_code=status.HTTP_201_CREATED, response_model=sch.FollowResponse)
async def follow(user_id:int,db:AsyncSession=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser),background_tasks:BackgroundTasks=BackgroundTasks(),_:None=Depends(follow_limiter)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToFollow=result.scalars().first()
    if not userToFollow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    if userToFollow.id == currentUser.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot follow yourself")
    # Check if already following via connections table
    existingConn=await db.execute(
        select(models.connections).where(
            and_(models.connections.c.followed_id==user_id, models.connections.c.follower_id==currentUser.id)
        )
    )
    if existingConn.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Your already following this user")
    try:
        # Direct INSERT into the connections association table
        await db.execute(insert(models.connections).values(followed_id=user_id, follower_id=currentUser.id))
        # Update counts via a count query for accuracy
        following_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.follower_id==currentUser.id))
        currentUser.following_cnt = following_cnt_result.scalar()
        followers_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.followed_id==user_id))
        userToFollow.followers_cnt = followers_cnt_result.scalar()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to follow user")
    # follower/following counts changed on both users — invalidate both profiles
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToFollow.id}")
    # Invalidate followers/following list caches
    await delete_cache(f"followers:{userToFollow.id}")
    await delete_cache(f"following:{currentUser.id}")
    # Invalidate home feed cache for the follower (new posts appear)
    await delete_cache_pattern(f"feed:home:{currentUser.id}:*")
    # Notify the followed user that someone started following them.
    # Self-follow is already prevented above, so no extra guard needed here.
    background_tasks.add_task(
        create_notification,
        actor_id=currentUser.id,
        owner_id=userToFollow.id,
        notif_type=NotificationType.follow,
        actor_username=currentUser.username,
        entity_id=None,
        entity_type=None,
    )
    return sch.FollowResponse(message=f"Followed user {userToFollow.username}", following_count=currentUser.following_cnt)
    
@router.delete("/unfollow/{user_id}",status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
async def unfollow(user_id:int,db:AsyncSession=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToUnFollow=result.scalars().first()
    if not userToUnFollow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    # Check if actually following via connections table
    existingConn=await db.execute(
        select(models.connections).where(
            and_(models.connections.c.followed_id==user_id, models.connections.c.follower_id==currentUser.id)
        )
    )
    if not existingConn.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Not following this user")
    try:
        # Direct DELETE from the connections association table
        await db.execute(
            delete(models.connections).where(
                and_(models.connections.c.followed_id==user_id, models.connections.c.follower_id==currentUser.id)
            )
        )
        # Update counts
        following_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.follower_id==currentUser.id))
        currentUser.following_cnt = following_cnt_result.scalar()
        followers_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.followed_id==user_id))
        userToUnFollow.followers_cnt = followers_cnt_result.scalar()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to unfollow user")
    # follower/following counts changed on both users — invalidate both profiles
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToUnFollow.id}")
    # Invalidate followers/following list caches
    await delete_cache(f"followers:{userToUnFollow.id}")
    await delete_cache(f"following:{currentUser.id}")
    await delete_cache_pattern(f"feed:home:{currentUser.id}:*")
    return sch.FollowResponse(message=f"Unfollowed user {userToUnFollow.username}", following_count=currentUser.following_cnt)

@router.delete("/remove_follower/{user_id}", status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
async def remove_follower(user_id: int, db: AsyncSession = Depends(getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.User).where(models.User.id == user_id))
    userToRemove=result.scalars().first()
    if not userToRemove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    # Check if this user is actually following me via connections table
    existingConn=await db.execute(
        select(models.connections).where(
            and_(models.connections.c.followed_id==currentUser.id, models.connections.c.follower_id==user_id)
        )
    )
    if not existingConn.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is not following you")

    try:
        # Direct DELETE from the connections association table
        await db.execute(
            delete(models.connections).where(
                and_(models.connections.c.followed_id==currentUser.id, models.connections.c.follower_id==user_id)
            )
        )
        
        # Update counts
        followers_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.followed_id==currentUser.id))
        currentUser.followers_cnt = followers_cnt_result.scalar()
        following_cnt_result = await db.execute(select(func.count()).select_from(models.connections).where(models.connections.c.follower_id==user_id))
        userToRemove.following_cnt = following_cnt_result.scalar()
        
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to remove follower")
    # follower/following counts changed on both users — invalidate both profiles
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToRemove.id}")
    # Invalidate followers/following list caches
    await delete_cache(f"followers:{currentUser.id}")
    await delete_cache(f"following:{userToRemove.id}")
    return sch.FollowResponse(message=f"Removed follower {userToRemove.username}", following_count=currentUser.following_cnt)

@router.get("/connections/users/{user_id}/followers", response_model=List[sch.UserBasicResponse])
async def get_followers(user_id:int,db:AsyncSession=Depends(getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get follower IDs from connections table, then load users
    followerResult = await db.execute(
        select(models.User).join(
            models.connections, models.connections.c.follower_id == models.User.id
        ).where(models.connections.c.followed_id == user_id)
    )
    followers = followerResult.scalars().all()
    
    # Get current user's following IDs for is_following check
    followingResult = await db.execute(
        select(models.connections.c.followed_id).where(models.connections.c.follower_id == currentUser.id)
    )
    current_following_ids = {row[0] for row in followingResult.all()}
    
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=(f.id in current_following_ids)
        ) for f in followers
    ]

@router.get("/connections/users/{user_id}/following", response_model=List[sch.UserBasicResponse])
async def get_following(user_id:int,db:AsyncSession=Depends(getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get following users from connections table
    followingResult = await db.execute(
        select(models.User).join(
            models.connections, models.connections.c.followed_id == models.User.id
        ).where(models.connections.c.follower_id == user_id)
    )
    following = followingResult.scalars().all()
    
    # Get current user's following IDs for is_following check
    currentFollowingResult = await db.execute(
        select(models.connections.c.followed_id).where(models.connections.c.follower_id == currentUser.id)
    )
    current_following_ids = {row[0] for row in currentFollowingResult.all()}
    
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=(f.id in current_following_ids)
        ) for f in following
    ]