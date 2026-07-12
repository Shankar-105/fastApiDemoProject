from fastapi import status,HTTPException,Depends,APIRouter,Request
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import List, Optional
from app.services.redis_service import delete_cache, delete_cache_pattern ,increment_cache_version
from app.services.idempotency_service import get_idempotency_key, idempotent
from app.models import NotificationType
from app.services.rate_limit_service import follow_limiter
from app.tasks.notification_tasks import create_notification_task
import structlog

router=APIRouter(
    prefix="/users",
    tags=['Connections']
)

logger = structlog.get_logger(__name__)

@router.post("/{user_id}/follow", status_code=status.HTTP_201_CREATED, response_model=sch.FollowResponse)
@idempotent(endpoint_identifier="follow_user", success_status_code=status.HTTP_201_CREATED)
async def follow_user(
        user_id: int,
    db:AsyncSession=Depends(getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    background_tasks=None,
    _:None=Depends(follow_limiter),
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("follow_user_attempt", user_id=currentUser.id, target_id=user_id)
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToFollow=result.scalars().first()
    if not userToFollow:
        logger.warning("follow_user_failed_not_found", target_id=user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    if userToFollow.id == currentUser.id:
        logger.warning("follow_user_failed_self", user_id=currentUser.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot follow yourself")
    try:
        insert_result = await db.execute(
            pg_insert(models.connections)
            .values(followed_id=user_id, follower_id=currentUser.id)
            .on_conflict_do_nothing(index_elements=[models.connections.c.followed_id, models.connections.c.follower_id])
            .returning(models.connections.c.followed_id)
        )
        if not insert_result.first():
            logger.warning("follow_user_failed_already_following", user_id=currentUser.id, target_id=user_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Your already following this user")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error("follow_user_failed_unexpected", user_id=currentUser.id, target_id=user_id)
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
    logger.info("follow_user_success", user_id=currentUser.id, target_id=user_id)
    return sch.FollowResponse(message=f"Followed user {userToFollow.username}", following_count=currentUser.following_cnt)
    
@router.delete("/{user_id}/unfollow", status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
@idempotent(endpoint_identifier="unfollow_user")
async def unfollow_user(
    user_id:int, 
    db:AsyncSession=Depends(getDb), 
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("unfollow_user_attempt", user_id=currentUser.id, target_id=user_id)
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    userToUnFollow=result.scalars().first()
    if not userToUnFollow:
        logger.warning("unfollow_user_failed_not_found", target_id=user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    try:
        delete_result = await db.execute(
            delete(models.connections)
            .where(
                and_(models.connections.c.followed_id==user_id, models.connections.c.follower_id==currentUser.id)
            )
            .returning(models.connections.c.followed_id)
        )
        if delete_result.rowcount == 0:
            logger.warning("unfollow_user_failed_not_following", user_id=currentUser.id, target_id=user_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="You are not following this user")
        
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error("unfollow_user_failed_unexpected", user_id=currentUser.id, target_id=user_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to unfollow user")
    
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{user_id}")
    await delete_cache(f"followers:{user_id}")
    await delete_cache(f"following:{currentUser.id}")
    await increment_cache_version("feed:home")
    logger.info("unfollow_user_success", user_id=currentUser.id, target_id=user_id)
    return sch.FollowResponse(message=f"Unfollowed user {userToUnFollow.username}", following_count=currentUser.following_cnt)

@router.delete("/{user_id}/followers/{follower_id}", status_code=status.HTTP_200_OK, response_model=sch.FollowResponse)
@idempotent(endpoint_identifier="remove_follower")
async def remove_follower_endpoint(
    user_id:int, 
    follower_id:int, 
    db: AsyncSession = Depends(getDb), 
    currentUser: models.User = Depends(oauth2.getCurrentUser),
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("remove_follower_attempt", user_id=currentUser.id, follower_id=follower_id)
    if user_id != currentUser.id:
        logger.warning("remove_follower_failed_unauthorized", user_id=currentUser.id, target_user_id=user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only remove followers from your own account")
    
    result=await db.execute(select(models.User).where(models.User.id == follower_id))
    userToRemove=result.scalars().first()
    if not userToRemove:
        logger.warning("remove_follower_failed_not_found", follower_id=follower_id)
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
            logger.warning("remove_follower_failed_not_following", user_id=currentUser.id, follower_id=follower_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is not following you")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.error("remove_follower_failed_unexpected", user_id=currentUser.id, follower_id=follower_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to remove follower")
    await delete_cache(f"user_profile:{currentUser.id}")
    await delete_cache(f"user_profile:{userToRemove.id}")
    await delete_cache(f"followers:{currentUser.id}")
    await delete_cache(f"following:{userToRemove.id}")
    logger.info("remove_follower_success", user_id=currentUser.id, follower_id=follower_id)
    return sch.FollowResponse(message=f"Removed follower {userToRemove.username}", following_count=currentUser.following_cnt)

@router.get("/{user_id}/followers", response_model=List[sch.UserBasicResponse])
async def get_followers_list(user_id:int, db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug("fetching_followers_list", user_id=user_id)
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        logger.warning("get_followers_failed_not_found", user_id=user_id)
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
    
    logger.info("followers_list_retrieved", user_id=user_id, count=len(followers))
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
    logger.debug("fetching_following_list", user_id=user_id)
    result=await db.execute(select(models.User).where(models.User.id==user_id))
    user=result.scalars().first()
    if not user:
        logger.warning("get_following_failed_not_found", user_id=user_id)
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
    
    logger.info("following_list_retrieved", user_id=user_id, count=len(following))
    return [
        sch.UserBasicResponse(
            id=f.id,
            username=f.username,
            nickname=f.nickname,
            profile_pic=f.profile_picture,
            is_following=bool(is_following)
        ) for f, is_following in following
    ]
