from fastapi import Body,HTTPException,status,APIRouter,Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,func
from app import oauth2,models,db,schemas as sch, config
from app.models import NotificationType
from app.rate_limiter import comment_limiter
from app.services.redis_service import get_cache, set_cache, delete_cache_pattern, increment_cache_version
from app.tasks.notification_tasks import create_notification_task

router=APIRouter(tags=['comment'])

@router.post("/comment/createComment",status_code=status.HTTP_201_CREATED, response_model=sch.CommentDetailResponse)
async def createComment(comment:sch.CommentCreateRequest=Body(...),db:AsyncSession=Depends(db.getDb),currentUser: models.User = Depends(oauth2.getCurrentUser),_:None=Depends(comment_limiter)):
    # Check if the post exists
    result = await db.execute(select(models.Post).where(models.Post.id == comment.post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id {comment.post_id} not found")
    if not post.enable_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"this post has comments disabled")
    # Create the comment
    new_comment =models.Comments(post_id=comment.post_id,user_id=currentUser.id,comment_content=comment.content)
    db.add(new_comment)
    await db.commit()
    
    # Invalidate cached comments for this post and post detail caches
    await delete_cache_pattern(f"comments:post:{comment.post_id}:*")
    await delete_cache_pattern(f"post:{comment.post_id}:*")
    
    # Use versioned cache keys instead of global feed:* invalidation (always enabled).
    await increment_cache_version("feed:home")
    await increment_cache_version("feed:explore")
    # Notify the post owner when someone comments on their post.
    # Guard: no self-notification if the post owner comments on their own post.
    if currentUser.id != post.user_id:
        create_notification_task.delay(
            actor_id=currentUser.id,
            owner_id=post.user_id,
            notif_type=NotificationType.comment.value,
            actor_username=currentUser.username,
            entity_id=comment.post_id,
            entity_type="post",
        )
    # Build proper response (no refresh needed)
    user = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    return sch.CommentDetailResponse(
        id=new_comment.id,
        post_id=new_comment.post_id,
        content=new_comment.comment_content,
        likes=new_comment.likes,
        created_at=new_comment.created_at,
        user=user
    )

@router.delete("/comments/delete_comment/{comment_id}",status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
async def deleteComment(comment_id:int,db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.Comments).where(and_(models.Comments.id==comment_id,models.Comments.user_id==currentUser.id)))
    commentTodelete=result.scalars().first()
    if not commentTodelete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {comment_id} not Found") 
    post_id = commentTodelete.post_id
    await db.delete(commentTodelete)
    await db.commit()
    # Invalidate cached comments for this post
    await delete_cache_pattern(f"comments:post:{post_id}:*")
    await delete_cache_pattern(f"post:{post_id}:*")
    return sch.SuccessResponse(message=f"Comment {comment_id} deleted successfully")

@router.patch("/comments/edit_comment/{comment_id}",status_code=status.HTTP_200_OK, response_model=sch.CommentDetailResponse)
async def editComment(comment_id:int,editInfo:sch.CommentUpdateRequest=Body(...),db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    result=await db.execute(select(models.Comments).where(and_(models.Comments.id==comment_id,models.Comments.user_id==currentUser.id)))
    commentToBeEdited=result.scalars().first()
    if not commentToBeEdited:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {comment_id} not Found")
    commentToBeEdited.comment_content=editInfo.comment_content
    await db.commit()
    
    # Invalidate cached comments for this post
    await delete_cache_pattern(f"comments:post:{commentToBeEdited.post_id}:*")
    
    # Build proper response (no refresh needed)
    user = sch.UserBasicResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        profile_pic=currentUser.profile_picture
    )
    
    return sch.CommentDetailResponse(
        id=commentToBeEdited.id,
        post_id=commentToBeEdited.post_id,
        content=commentToBeEdited.comment_content,
        likes=commentToBeEdited.likes,
        created_at=commentToBeEdited.created_at,
        user=user
    )

@router.get("/comments-on/{post_id}", response_model=sch.CommentListResponse)
async def getAllPosts(post_id:int,
    limit:int=Query(10, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    # Check Redis cache first
    cache_key = f"comments:post:{post_id}:{offset}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    # P2.2: Fetch only needed columns
    # P2.3: Use limit+1 for has_more check instead of COUNT
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
        .limit(limit + 1)  # fetch one extra
    )
    paginatedComments=commentsResult.all()
    has_more = len(paginatedComments) > limit
    paginatedComments = paginatedComments[:limit]
    
    # Build proper response
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
        total=None,  # omit expensive count
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    result = sch.CommentListResponse(
        comments=commentsResponse,
        pagination=pagination
    )
    await set_cache(cache_key, result.model_dump(mode="json"), ttl=30)
    return result
