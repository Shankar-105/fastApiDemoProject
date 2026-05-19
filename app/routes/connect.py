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
from app.services.rate_limit_service import follow_limiter
from app.tasks.notification_tasks import create_notification_task
import logging

router=APIRouter(
    prefix="/users",
    tags=['Connections']
)

logger = logging.getLogger("app")

@router.post("/{user_id}/follow", status_code=status.HTTP_201_CREATED, response_model=sch.FollowResponse)
async def follow_user(user_id:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser), background_tasks=None, _:None=Depends(follow_limiter)):
    logger.info(f"User {currentUser.id} attempting to follow user {user_id}")
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToFollow=result.scalars().first()
    if not userToFollow:
        logger.warning(f"Follow failed - user {user_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    if userToFollow.id == currentUser.id:
        logger.warning(f"Follow failed - user {currentUser.id} attempted to follow themselves")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot follow yourself")
    try:
        insert_result = await db.execute(
            pg_insert(models.connections)
            .values(followed_id=user_id, follower_id=currentUser.id)
            .on_conflict_do_nothing(index_elements=[models.connections.c.followed_id, models.connections.c.follower_id])
            .returning(models.connections.c.followed_id)
        )
        if not insert_result.first():
            logger.warning(f"Follow failed - user {currentUser.id} already following user {user_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Your already following this user")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error(f"Follow failed - unexpected error for user {currentUser.id} following user {user_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to follow user")
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToFollow.id}")
    await delete_cache(f"followers:{userToFollow.id}")
    await delete_cache(f"following:{currentUser.id}")
    await delete_cache_pattern(f"feed:home:{currentUser.id}:*")
    create_notification_task.delay(
        actor_id=currentUser.id,
        owner_id=userToFollow.id,
        notif_type=NotificationType.follow.value,
        actor_username=currentUser.username,
        entity_id=None,
        entity_type=None,
    )
    logger.info(f"User {currentUser.id} successfully followed user {user_id}")
    return sch.FollowResponse(message=f"Followed user {userToFollow.username}", following_count=currentUser.following_cnt)
    
@router.delete("/{user_id}/unfollow", status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
async def unfollow_user(user_id:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} attempting to unfollow user {user_id}")
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToUnFollow=result.scalars().first()
    if not userToUnFollow:
        logger.warning(f"Unfollow failed - user {user_id} does not exist")
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
            logger.warning(f"Unfollow failed - user {currentUser.id} not following user {user_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Not following this user")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error(f"Unfollow failed - unexpected error for user {currentUser.id} unfollowing user {user_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to unfollow user")
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToUnFollow.id}")
    await delete_cache(f"followers:{userToUnFollow.id}")
    await delete_cache(f"following:{currentUser.id}")
    await delete_cache_pattern(f"feed:home:{currentUser.id}:*")
    logger.info(f"User {currentUser.id} successfully unfollowed user {user_id}")
    return sch.FollowResponse(message=f"Unfollowed user {userToUnFollow.username}", following_count=currentUser.following_cnt)

@router.delete("/{user_id}/followers/{follower_id}", status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
async def remove_follower_endpoint(user_id:int, follower_id:int, db: AsyncSession = Depends(getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} attempting to remove follower {follower_id}")
    if user_id != currentUser.id:
        logger.warning(f"Remove follower failed - user {currentUser.id} attempted to remove follower for user {user_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only remove followers from your own account")
    
    result=await db.execute(select(models.User).where(models.User.id == follower_id))
    userToRemove=result.scalars().first()
    if not userToRemove:
        logger.warning(f"Remove follower failed - user {follower_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    try:
        delete_result = await db.execute(
            delete(models.connections)
            .where(
                and_(models.connections.c.followed_id==currentUser.id, models.connections.c.follower_id==follower_id)
            )
            .returning(models.connections.c.follower_id)
        )
        if not delete_result.first():
            logger.warning(f"Remove follower failed - user {follower_id} is not following user {currentUser.id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is not following you")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error(f"Remove follower failed - unexpected error for user {currentUser.id} removing follower {follower_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to remove follower")
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToRemove.id}")
    await delete_cache(f"followers:{currentUser.id}")
    await delete_cache(f"following:{userToRemove.id}")
    logger.info(f"User {currentUser.id} successfully removed follower {follower_id}")
    return sch.FollowResponse(message=f"Removed follower {userToRemove.username}", following_count=currentUser.following_cnt)

@router.get("/{user_id}/followers", response_model=List[sch.UserBasicResponse])
async def get_followers_list(user_id:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching followers list for user {user_id}")
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        logger.warning(f"Get followers failed - user {user_id} does not exist")
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
    
    logger.info(f"Followers list retrieved for user {user_id}, count: {len(followers)}")
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=bool(is_following)
        ) for f, is_following in followers
    ]

@router.get("/{user_id}/following", response_model=List[sch.UserBasicResponse])
async def get_following_list(user_id:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug(f"Fetching following list for user {user_id}")
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        logger.warning(f"Get following failed - user {user_id} does not exist")
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
    
    logger.info(f"Following list retrieved for user {user_id}, count: {len(following)}")
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=bool(is_following)
        ) for f, is_following in following
    ]
