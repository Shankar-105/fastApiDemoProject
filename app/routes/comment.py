from fastapi import Body,HTTPException,status,APIRouter,Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,func
from app import oauth2,models,db,schemas as sch, config
from app.models import NotificationType
from app.services.rate_limit_service import comment_limiter
from app.services.redis_service import get_cache, set_cache, delete_cache_pattern, increment_cache_version
from app.tasks.notification_tasks import create_notification_task
import logging

router=APIRouter(
    prefix="",
    tags=['Comments']
)

logger = logging.getLogger("app")

@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED, response_model=sch.CommentDetailResponse)
async def create_comment(post_id:int, comment:sch.CommentCreateRequest=Body(...), db:AsyncSession=Depends(db.getDb), currentUser: models.User = Depends(oauth2.getCurrentUser), _:None=Depends(comment_limiter)):
    logger.info(f"User {currentUser.id} creating comment on post {post_id}")
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        logger.warning(f"Comment creation failed - post not found: {post_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id {post_id} not found")
    if not post.enable_comments:
        logger.warning(f"Comment creation failed - comments disabled on post {post_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"this post has comments disabled")
    new_comment =models.Comments(post_id=post_id,user_id=currentUser.id,comment_content=comment.content)
    db.add(new_comment)
    await db.commit()
    
    await delete_cache_pattern(f"comments:post:{post_id}:*")
    await delete_cache_pattern(f"post:{post_id}:*")
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    if currentUser.id != post.user_id:
        create_notification_task.delay(
            actor_id=currentUser.id,
            owner_id=post.user_id,
            notif_type=NotificationType.comment.value,
            actor_username=currentUser.username,
            entity_id=post_id,
            entity_type="post",
        )
    user = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    logger.info(f"User {currentUser.id} created comment {new_comment.id} on post {post_id}")
    return sch.CommentDetailResponse(
        id=new_comment.id,
        post_id=new_comment.post_id,
        content=new_comment.comment_content,
        likes=new_comment.likes,
        created_at=new_comment.created_at,
        user=user
    )

@router.delete("/comments/{commentId}", status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
async def delete_comment(commentId:int, db:AsyncSession=Depends(db.getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} deleting comment {commentId}")
    result=await db.execute(select(models.Comments).where(and_(models.Comments.id==commentId,models.Comments.user_id==currentUser.id)))
    commentTodelete=result.scalars().first()
    if not commentTodelete:
        logger.warning(f"Comment deletion failed - comment {commentId} not found or no permission")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {commentId} not Found") 
    post_id = commentTodelete.post_id
    await db.delete(commentTodelete)
    await db.commit()
    await delete_cache_pattern(f"comments:post:{post_id}:*")
    await delete_cache_pattern(f"post:{post_id}:*")
    logger.info(f"User {currentUser.id} deleted comment {commentId}")
    return sch.SuccessResponse(message=f"Comment {commentId} deleted successfully")

@router.patch("/comments/{commentId}", status_code=status.HTTP_200_OK, response_model=sch.CommentDetailResponse)
async def update_comment(commentId:int, request:sch.CommentUpdateRequest=Body(...), db:AsyncSession=Depends(db.getDb), currentUser: models.User = Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} updating comment {commentId}")
    result=await db.execute(select(models.Comments).where(and_(models.Comments.id==commentId,models.Comments.user_id==currentUser.id)))
    commentToBeEdited=result.scalars().first()
    if not commentToBeEdited:
        logger.warning(f"Comment update failed - comment {commentId} not found or no permission")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {commentId} not Found")
    commentToBeEdited.comment_content=request.comment_content
    await db.commit()
    
    await delete_cache_pattern(f"comments:post:{commentToBeEdited.post_id}:*")
    
    user = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    logger.info(f"User {currentUser.id} updated comment {commentId}")
    return sch.CommentDetailResponse(
        id=commentToBeEdited.id,
        post_id=commentToBeEdited.post_id,
        content=commentToBeEdited.comment_content,
        likes=commentToBeEdited.likes,
        created_at=commentToBeEdited.created_at,
        user=user
    )

@router.get("/posts/{post_id}/comments", response_model=sch.CommentListResponse)
async def get_post_comments(post_id:int, limit:int=Query(10, ge=1, le=100), offset: int = Query(0, ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    logger.debug(f"Fetching comments for post {post_id}, limit: {limit}, offset: {offset}")
    cache_key = f"comments:post:{post_id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"Comments for post {post_id} retrieved from cache")
        return cached

    commentsResult=await db.execute(
        select(
            models.Comments.id,
            models.Comments.post_id,
            models.Comments.comment_content,
            models.Comments.likes,
            models.Comments.created_at,
            models.User.id.label("user_id"),
            models.User.username,
            models.User.nickname,
            models.User.profile_picture,
        )
        .join(models.User, models.User.id == models.Comments.user_id)
        .where(models.Comments.post_id==post_id)
        .order_by(models.Comments.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    paginatedComments=commentsResult.all()
    has_more = len(paginatedComments) > limit
    paginatedComments = paginatedComments[:limit]
    
    commentsResponse = []
    for row in paginatedComments:
        user = sch.UserBasicResponse(
            id=row.user_id,
            username=row.username,
            nickname=row.nickname,
            profile_pic=row.profile_picture
        )
        commentsResponse.append(sch.CommentDetailResponse(
            id=row.id,
            post_id=row.post_id,
            content=row.comment_content,
            likes=row.likes,
            created_at=row.created_at,
            user=user
        ))
    
    pagination = sch.PaginationMetadata(
        total=None,
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    result = sch.CommentListResponse(
        comments=commentsResponse,
        pagination=pagination
    )
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=30)
    logger.info(f"Comments for post {post_id} retrieved from DB, count: {len(commentsResponse)}")
    return result
