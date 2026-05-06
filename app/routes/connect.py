from fastapi import status,HTTPException,Depends,APIRouter
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import List
from app.services.redis_service import delete_cache, delete_cache_pattern
from app.models import NotificationType
from app.rate_limiter import follow_limiter
from app.tasks.notification_tasks import create_notification_task

router=APIRouter(tags=['connections'])

@router.post("/follow/{user_id}",status_code=status.HTTP_201_CREATED, response_model=sch.FollowResponse)
async def follow(user_id:int,db:AsyncSession=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser),background_tasks=None,_:None=Depends(follow_limiter)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToFollow=result.scalars().first()
    if not userToFollow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    if userToFollow.id == currentUser.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot follow yourself")
    try:
        insert_result = await db.execute(
            pg_insert(models.connections)
            .values(followed_id=user_id, follower_id=currentUser.id)
            .on_conflict_do_nothing(index_elements=[models.connections.c.followed_id, models.connections.c.follower_id])
            .returning(models.connections.c.followed_id)
        )
        if not insert_result.first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Your already following this user")

        await db.commit()
        await db.refresh(currentUser)
        await db.refresh(userToFollow)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to follow user")
    # follower/following counts changed on both users - invalidate both profiles
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToFollow.id}")
    # Invalidate followers/following list caches
    await delete_cache(f"followers:{userToFollow.id}")
    await delete_cache(f"following:{currentUser.id}")
    # Invalidate home feed cache for the follower (new posts appear)
    await delete_cache_pattern(f"feed:home:{currentUser.id}:*")
    # Notify the followed user that someone started following them.
    # Self-follow is already prevented above, so no extra guard needed here.
    create_notification_task.delay(
        actor_id=currentUser.id,
        owner_id=userToFollow.id,
        notif_type=NotificationType.follow.value,
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
    try:
        delete_result = await db.execute(
            delete(models.connections)
            .where(
                and_(models.connections.c.followed_id==user_id, models.connections.c.follower_id==currentUser.id)
            )
            .returning(models.connections.c.followed_id)
        )
        if not delete_result.first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Not following this user")

        await db.commit()
        await db.refresh(currentUser)
        await db.refresh(userToUnFollow)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to unfollow user")
    # follower/following counts changed on both users - invalidate both profiles
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
    
    try:
        delete_result = await db.execute(
            delete(models.connections)
            .where(
                and_(models.connections.c.followed_id==currentUser.id, models.connections.c.follower_id==user_id)
            )
            .returning(models.connections.c.follower_id)
        )
        if not delete_result.first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is not following you")

        await db.commit()
        await db.refresh(currentUser)
        await db.refresh(userToRemove)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to remove follower")
    # follower/following counts changed on both users - invalidate both profiles
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
    
    follower_link = models.connections.alias("follower_link")
    current_link = models.connections.alias("current_following_link")
    is_following = (
        select(current_link.c.followed_id)
        .where(
            current_link.c.follower_id == currentUser.id,
            current_link.c.followed_id == models.User.id,
        )
        .exists()
        .label("is_following")
    )
    followerResult = await db.execute(
        select(models.User, is_following)
        .join(follower_link, follower_link.c.follower_id == models.User.id)
        .where(follower_link.c.followed_id == user_id)
    )
    followers = followerResult.all()
    
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=bool(is_following)
        ) for f, is_following in followers
    ]

@router.get("/connections/users/{user_id}/following", response_model=List[sch.UserBasicResponse])
async def get_following(user_id:int,db:AsyncSession=Depends(getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    following_link = models.connections.alias("following_link")
    current_link = models.connections.alias("current_following_link")
    is_following = (
        select(current_link.c.followed_id)
        .where(
            current_link.c.follower_id == currentUser.id,
            current_link.c.followed_id == models.User.id,
        )
        .exists()
        .label("is_following")
    )
    followingResult = await db.execute(
        select(models.User, is_following)
        .join(following_link, following_link.c.followed_id == models.User.id)
        .where(following_link.c.follower_id == user_id)
    )
    following = followingResult.all()
    
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=bool(is_following)
        ) for f, is_following in following
    ]
