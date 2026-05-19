from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2, config
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
from sqlalchemy.exc import IntegrityError
from app.models import NotificationType
from app.services.redis_service import delete_cache_pattern, increment_cache_version
from app.tasks.notification_tasks import create_notification_task
import logging

router=APIRouter(
    prefix="",
    tags=['Votes']
)

logger = logging.getLogger("app")

@router.post("/posts/{postId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
async def voteOnPost(postId:int, post:sch.VoteRequest=Body(...), db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} voting on post {postId} with choice {post.choice}")
    if post.post_id != postId:
        logger.warning(f"Vote failed - path/post_id mismatch: {postId} vs {post.post_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path postId and request post_id must match")
    result=await db.execute(select(models.Post).where(models.Post.id==post.post_id))
    queriedPost=result.scalars().first()
    if not queriedPost:
        logger.warning(f"Vote failed - post not found: {post.post_id}")
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
                logger.info(f"User {currentUser.id} removed vote on post {postId}")
                return sch.VoteResponse(message="Vote removed successfully", likes=likes, dislikes=dislikes)
            else:
                currentVote.action = post.choice
                await db.commit()
                count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
                likes, dislikes = count_result.first()
                await delete_cache_pattern(f"post:{post.post_id}:*")
                await increment_cache_version("feed:home")
                await increment_cache_version("feed:explore")
                logger.info(f"User {currentUser.id} switched vote on post {postId} to {post.choice}")
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
            logger.info(f"User {currentUser.id} added vote on post {postId}")
            return sch.VoteResponse(message="New vote added successfully", likes=likes, dislikes=dislikes)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Vote failed - integrity error for user {currentUser.id} on post {postId}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
@router.post("/comments/{commentId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
async def likeAComment(commentId:int, comment:sch.CommentVoteRequest=Body(...), db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    logger.info(f"User {currentUser.id} voting on comment {commentId} with choice {comment.choice}")
    if comment.comment_id != commentId:
        logger.warning(f"Comment vote failed - path/comment_id mismatch: {commentId} vs {comment.comment_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path commentId and request comment_id must match")
    result=await db.execute(select(models.Comments).where(models.Comments.id==comment.comment_id))
    queriedComment=result.scalars().first()
    if not queriedComment:
        logger.warning(f"Comment vote failed - comment not found: {comment.comment_id}")
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
                logger.info(f"User {currentUser.id} removed vote on comment {commentId}")
                return sch.VoteResponse(message="Vote removed successfully", likes=likes)
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
            logger.info(f"User {currentUser.id} added vote on comment {commentId}")
            return sch.VoteResponse(message="New vote added successfully", likes=likes)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Comment vote failed - integrity error for user {currentUser.id} on comment {commentId}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
