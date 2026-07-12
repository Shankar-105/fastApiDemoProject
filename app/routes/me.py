from fastapi import status,HTTPException,Depends,Body,APIRouter,Form,Query,Request
from fastapi.responses import FileResponse
import app.schemas as sch
from typing import List, Optional
from app import models,db,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,distinct,func,case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
import os
import asyncio
from fastapi import UploadFile,File
from app.services.redis_service import delete_cache
from app.services.idempotency_service import get_idempotency_key, idempotent
from app.services.blob_service import upload_blob, delete_blob, get_blob_url
from app.services.concurrency_service import lock_user_row, run_with_transient_retry
import structlog

router=APIRouter(
    prefix="/users/me",
    tags=['Current User']
)

logger = structlog.get_logger(__name__)

@router.get("/profile", status_code=status.HTTP_200_OK, response_model=sch.UserProfileResponse)
async def myProfile(db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug("fetching_my_profile", user_id=currentUser.id)
    posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
    posts_count = posts_count_result.scalar()
    logger.info("my_profile_retrieved", user_id=currentUser.id)
    return sch.UserProfileResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        bio=currentUser.bio or "",
        profile_picture=currentUser.profile_picture,
        posts_count=posts_count,
        followers_count=currentUser.followers_cnt,
        following_count=currentUser.following_cnt,
        created_at=currentUser.created_at
    )

@router.get("/avatar", status_code=status.HTTP_200_OK, response_model=sch.MediaInfo)
async def get_current_user_avatar(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug("fetching_my_avatar", user_id=currentUser.id)
    profilePicturePath = currentUser.profile_picture
    if not profilePicturePath:
        logger.warning("my_avatar_not_found", user_id=currentUser.id)
        raise HTTPException(status_code=404, detail="No profile picture")
    logger.info("my_avatar_retrieved", user_id=currentUser.id)
    return sch.MediaInfo(
        url=get_blob_url("profilepics", profilePicturePath),
        type="image"
    )

@router.delete("/avatar", status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
@idempotent(endpoint_identifier="delete_profile_picture")
async def delete_profile_picture(
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("delete_profile_picture_attempt", user_id=currentUser.id)
    async def _remove_picture():
        locked_user = await lock_user_row(db, user_id=currentUser.id)
        profilePic = locked_user.profile_picture
        if not profilePic:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="No profile picture to remove")
        locked_user.profile_picture = None
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile was updated concurrently")
        return locked_user, profilePic

    currentUser, old_profile_pic = await run_with_transient_retry(lambda: _remove_picture(), db=db)
    if old_profile_pic:
        await delete_blob("profilepics", old_profile_pic)
    await delete_cache(f"user_profile:{currentUser.id}")
    logger.info("profile_picture_removed", user_id=currentUser.id)
    return sch.SuccessResponse(message="Profile picture removed successfully")

# retrives all posts using sqlAlchemy
@router.get("/posts", response_model=sch.PostListResponse)
async def get_current_user_posts(limit:int=Query(10, ge=1, le=100), offset: int = Query(0, ge=0), db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.debug("fetching_my_posts", user_id=currentUser.id, limit=limit, offset=offset)
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
        select(
            models.Post.id,
            models.Post.title,
            models.Post.media_path,
            models.Post.media_type,
            models.Post.likes,
            models.Post.comments_cnt,
            models.Post.created_at,
            is_liked
        )
        .where(models.Post.user_id==currentUser.id)
        .order_by(models.Post.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    paginatedPosts=postsResult.all()
    has_more = len(paginatedPosts) > limit
    paginatedPosts = paginatedPosts[:limit]
    
    posts = []
    for row in paginatedPosts:
        media_url = None
        if row.media_path:
            media_url = get_blob_url("posts-media", row.media_path)
        posts.append(sch.PostListItemResponse(
            id=row.id,
            title=row.title,
            media_url=media_url,
            media_type=row.media_type,
            likes=row.likes,
            comments_count=row.comments_cnt,
            created_at=row.created_at,
            is_liked=bool(row.is_liked) if row.is_liked is not None else False
        ))
    
    pagination = sch.PaginationMetadata(
        total=None,
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    logger.info("my_posts_retrieved", user_id=currentUser.id, count=len(posts))
    return sch.PostListResponse(
        posts=posts,
        pagination=pagination
    )
# a patch endpoint so that user can update what he wants to unlike put
# profile picture cannot be taken as a json data so it must be passed via Form
# and the username and bio can be passed via Body params but its resulting in an
# ambiguity as one of the section is being passed via Form and the other via Body
# so made everything to be passed via Form only
@router.patch("", status_code=status.HTTP_200_OK, response_model=sch.UserProfileResponse)
@idempotent(endpoint_identifier="update_profile")
async def update_current_user_profile(
    username:str=Form(None),
    bio:str=Form(None),
    profile_picture:UploadFile=File(None),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    token: str = Depends(oauth2.oauth2_scheme),
    request: Optional[Request] = None,
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    logger.info("update_my_profile_attempt", user_id=currentUser.id)
    if not any([username, bio, profile_picture]):
        posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
        posts_count = posts_count_result.scalar()
        return sch.UserProfileResponse(
            id=currentUser.id,
            username=currentUser.username,
            nickname=currentUser.nickname,
            bio=currentUser.bio,
            profile_picture=currentUser.profile_picture,
            posts_count=posts_count,
            followers_count=currentUser.followers_cnt,
            following_count=currentUser.following_cnt,
            created_at=currentUser.created_at
        )

    async def _update_profile():
        locked_user = await lock_user_row(db, user_id=currentUser.id)
        previous_profile_picture = locked_user.profile_picture
        uploaded_blob_name = None
        if username:
            dupResult=await db.execute(select(models.User).where(models.User.username == username,models.User.id !=locked_user.id))
            if dupResult.scalars().first():
                await db.rollback()
                raise HTTPException(status_code=400, detail="Username already taken")
            locked_user.username = username
        if bio:
            locked_user.bio = bio
        if profile_picture:
            allowedFileTypes=['image/jpeg','image/png','image/gif']
            if profile_picture.content_type not in allowedFileTypes:
                await db.rollback()
                raise HTTPException(status_code=400,detail="only jpeg,png,gif files allowed")
            blob_name=f"{locked_user.username}_{profile_picture.filename}"
            content_bytes = await profile_picture.read()
            await upload_blob("profilepics", blob_name, content_bytes, profile_picture.content_type)
            uploaded_blob_name = blob_name
            locked_user.profile_picture=blob_name
        if username or bio or profile_picture:
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                if uploaded_blob_name:
                    await delete_blob("profilepics", uploaded_blob_name)
                raise HTTPException(status_code=400, detail="Username already taken")
            except StaleDataError:
                await db.rollback()
                if uploaded_blob_name:
                    await delete_blob("profilepics", uploaded_blob_name)
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile was updated concurrently")
            await db.refresh(locked_user)
            if previous_profile_picture and previous_profile_picture != locked_user.profile_picture:
                await delete_blob("profilepics", previous_profile_picture)
            await delete_cache(f"user_profile:{locked_user.id}")
        else:
            await db.rollback()
        return locked_user

    currentUser = await run_with_transient_retry(lambda: _update_profile(), db=db)
    await delete_cache(f"auth:user:{token}")
    
    posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
    posts_count = posts_count_result.scalar()
    
    logger.info("update_my_profile_success", user_id=currentUser.id)
    return sch.UserProfileResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        bio=currentUser.bio,
        profile_picture=currentUser.profile_picture,
        posts_count=posts_count,
        followers_count=currentUser.followers_cnt,
        following_count=currentUser.following_cnt,
        created_at=currentUser.created_at
    )

@router.get("/engagements/votes", status_code=status.HTTP_200_OK)
async def get_voted_posts(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Query voted posts via join
    result=await db.execute(
        select(models.Post.title, models.Post.id, models.User.username)
        .join(models.Votes, models.Votes.post_id==models.Post.id)
        .join(models.User, models.User.id==models.Post.user_id)
        .where(models.Votes.user_id==currentUser.id)
    )
    voted_posts=result.all()
    return {
                f"{currentUser.username} you have voted on posts":
            [
                {
                "post title":f"{post_title}",
                "post id":f"{post_id}",
                "post owner":f"{post_owner}"
            } 
                for post_title, post_id, post_owner in voted_posts
        ]
    }

@router.get("/stats/votes", status_code=status.HTTP_200_OK, response_model=sch.VoteStatsResponse)
async def get_vote_stats(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # using the func,case and quering - BUG FIX: summary returns a list of Row objects
    result=await db.execute(
        select(
            func.count(case((models.Votes.action==True, 1))).label("likes"),
            func.count(case((models.Votes.action==False, 1))).label("dislikes")
        ).where(models.Votes.user_id==currentUser.id)
    )
    summary=result.first()
    
    return sch.VoteStatsResponse(
        liked_posts_count=summary.likes if summary else 0,
        disliked_posts_count=summary.dislikes if summary else 0
    )

@router.get("/posts/liked")
async def get_liked_posts_list(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Query liked posts
    result=await db.execute(
        select(models.Post.id, models.User.username)
        .join(models.Votes, models.Votes.post_id==models.Post.id)
        .join(models.User, models.User.id==models.Post.user_id)
        .where(and_(models.Votes.user_id==currentUser.id, models.Votes.action==True))
    )
    liked_posts=result.all()
    return {
        f"{currentUser.username} your liked posts includes":
        [
            {
                "post id":post_id,
                "post owner":post_owner
            }
            for post_id, post_owner in liked_posts
        ]
    }
@router.get("/posts/disliked")
async def get_disliked_posts_list(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):    # Query disliked posts
    result=await db.execute(
        select(models.Post.id, models.User.username)
        .join(models.Votes,models.Votes.post_id==models.Post.id)
        .join(models.User, models.User.id==models.Post.user_id)
        .where(and_(models.Votes.user_id==currentUser.id, models.Votes.action==False))
    )
    disliked_posts=result.all()
    return {
        f"{currentUser.username} your disliked posts includes":
        [
            {
                "post id":post_id,
                "post owner":post_owner
            }
            for post_id, post_owner in disliked_posts
        ]
    }

@router.get("/posts/commented", status_code=status.HTTP_200_OK)
async def get_commented_posts(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    postsResult=await db.execute(
        select(models.Post.title, models.Post.id, models.User.username)
        .join(models.Comments, models.Comments.post_id == models.Post.id)
        .join(models.User, models.User.id == models.Post.user_id)
        .where(models.Comments.user_id==currentUser.id)
        .group_by(models.Post.id, models.Post.title, models.User.username)
    )
    commented_posts=postsResult.all()
    return {
                f"{currentUser.username} you have commented on posts":
            [
                {
                "post title":f"{post_title}",
                "post id":f"{post_id}",
                "post owner":f"{post_owner}"
            } 
                for post_title, post_id, post_owner in commented_posts
        ]
    }

@router.get("/stats/comments", status_code=status.HTTP_200_OK, response_model=sch.CommentStatsResponse)
async def get_comment_stats(db:AsyncSession=Depends(db.getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Fetch both aggregates in one query to reduce DB roundtrips.
    statsResult=await db.execute(
        select(
            func.count(models.Comments.id).label("comment_count"),
            func.count(distinct(models.Comments.post_id)).label("unique_post_count"),
        ).where(models.Comments.user_id==currentUser.id)
    )
    stats = statsResult.first()
    return sch.CommentStatsResponse(
        total_comments=stats.comment_count if stats else 0,
        unique_posts_commented=stats.unique_post_count if stats else 0
    )
