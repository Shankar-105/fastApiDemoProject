from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import Optional
import app.schemas as sch
from app import models,oauth2, config
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
from sqlalchemy.exc import IntegrityError
from app.models import NotificationType
from app.services.redis_service import delete_cache_pattern, increment_cache_version
from app.services.idempotency_service import get_idempotency_key, idempotent
from app.tasks.notification_tasks import create_notification_task
import structlog

router=APIRouter(
    prefix="",
    tags=['Votes']
)

logger = structlog.get_logger(__name__)

@router.post("/posts/{postId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
@idempotent(endpoint_identifier="vote_on_post")
async def voteOnPost(
    postId:int,
    post:sch.VoteRequest=Body(...),
    db:AsyncSession=Depends(getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """Like, dislike, toggle, or remove a vote on a post.

    Three-way logic: no existing vote → create; same action → remove
    (toggle off); different action → switch.  Validates the path
    ``postId`` matches the payload ``post_id``.  Sends a ``like``
    notification on new likes only.  Invalidates post cache and feeds.
    """
    logger.info("vote_post_attempt", user_id=currentUser.id, post_id=postId, choice=post.choice)
    if post.post_id != postId:
        logger.warning("vote_post_mismatch", post_id_path=postId, post_id_payload=post.post_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path postId and request post_id must match")
    result=await db.execute(select(models.Post).where(models.Post.id==post.post_id))
    queriedPost=result.scalars().first()
    if not queriedPost:
        logger.warning("vote_post_not_found", post_id=post.post_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {post.post_id} not Found")
    voteResult=await db.execute(select(models.Votes).where(and_(models.Votes.post_id==post.post_id,models.Votes.user_id==currentUser.id)))
    currentVote=voteResult.scalars().first()
    try:
        if currentVote:
            if currentVote.action == post.choice:
                await db.delete(currentVote)
                await db.commit()
                count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
                likes, dislikes = count_result.first()
                await delete_cache_pattern(f"post:{post.post_id}:*")
                await increment_cache_version("feed:home")
                await increment_cache_version("feed:explore")
                logger.info("vote_post_removed", user_id=currentUser.id, post_id=postId)
                return sch.VoteResponse(message="Vote removed successfully", likes=likes, dislikes=dislikes)
            else:
                currentVote.action = post.choice
                await db.commit()
                count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
                likes, dislikes = count_result.first()
                await delete_cache_pattern(f"post:{post.post_id}:*")
                await increment_cache_version("feed:home")
                await increment_cache_version("feed:explore")
                logger.info("vote_post_switched", user_id=currentUser.id, post_id=postId, choice=post.choice)
                return sch.VoteResponse(message="Vote switched successfully", likes=likes, dislikes=dislikes)
        else:
            newVote = models.Votes(
                post_id=post.post_id,
                user_id=currentUser.id,
                action=post.choice
            )
            db.add(newVote)
            await db.commit()
            count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
            likes, dislikes = count_result.first()
            await delete_cache_pattern(f"post:{post.post_id}:*")
            await increment_cache_version("feed:home")
            await increment_cache_version("feed:explore")
            if post.choice and currentUser.id != queriedPost.user_id:
                create_notification_task.delay(
                    actor_id=currentUser.id,
                    owner_id=queriedPost.user_id,
                    notif_type=NotificationType.like.value,
                    actor_username=currentUser.username,
                    entity_id=post.post_id,
                    entity_type="post",
                )
            logger.info("vote_post_added", user_id=currentUser.id, post_id=postId, choice=post.choice)
            return sch.VoteResponse(message="New vote added successfully", likes=likes, dislikes=dislikes)
    except IntegrityError:
        await db.rollback()
        logger.error("vote_post_integrity_error", user_id=currentUser.id, post_id=postId)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
@router.post("/comments/{commentId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
@idempotent(endpoint_identifier="vote_on_comment")
async def likeAComment(
    commentId:int,
    comment:sch.CommentVoteRequest=Body(...),
    db:AsyncSession=Depends(getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """Like, toggle, or remove a vote on a comment.

    Same three-way toggle pattern as ``voteOnPost`` but for comments
    and does *not* invalidate feed caches (comment votes are less
    visible).  Validates the path ``commentId`` matches the payload.
    """
    logger.info("vote_comment_attempt", user_id=currentUser.id, comment_id=commentId, choice=comment.choice)
    if comment.comment_id != commentId:
        logger.warning("vote_comment_mismatch", comment_id_path=commentId, comment_id_payload=comment.comment_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path commentId and request comment_id must match")
    result=await db.execute(select(models.Comments).where(models.Comments.id==comment.comment_id))
    queriedComment=result.scalars().first()
    if not queriedComment:
        logger.warning("vote_comment_not_found", comment_id=comment.comment_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {comment.comment_id} not Found")
    voteResult=await db.execute(select(models.CommentVotes).where(and_(models.CommentVotes.comment_id==comment.comment_id,models.CommentVotes.user_id==currentUser.id)))
    currentVote=voteResult.scalars().first()
    try:
        if currentVote:
            if currentVote.like==comment.choice:
                await db.delete(currentVote)
                await db.commit()
                count_result = await db.execute(select(models.Comments.likes).where(models.Comments.id==comment.comment_id))
                likes = count_result.scalar()
                logger.info("vote_comment_removed", user_id=currentUser.id, comment_id=commentId)
                return sch.VoteResponse(message="Vote removed successfully", likes=likes)
            else:
                currentVote.like=comment.choice
                await db.commit()
                count_result = await db.execute(select(models.Comments.likes).where(models.Comments.id==comment.comment_id))
                likes = count_result.scalar()
                logger.info("vote_comment_switched", user_id=currentUser.id, comment_id=commentId, choice=comment.choice)
                return sch.VoteResponse(message="Vote switched successfully", likes=likes)
        else:
            newVote=models.CommentVotes(
                comment_id=comment.comment_id,
                user_id=currentUser.id,
                like=comment.choice
            )
            db.add(newVote)
            await db.commit()
            count_result = await db.execute(select(models.Comments.likes).where(models.Comments.id==comment.comment_id))
            likes = count_result.scalar()
            logger.info("vote_comment_added", user_id=currentUser.id, comment_id=commentId, choice=comment.choice)
            return sch.VoteResponse(message="New vote added successfully", likes=likes)
    except IntegrityError:
        await db.rollback()
        logger.error("vote_comment_integrity_error", user_id=currentUser.id, comment_id=commentId)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
