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

router=APIRouter(
    prefix="/v1",
    tags=['Votes']
)

@router.post("/posts/{postId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
# get the post user that user wants to vote on with which user he is
async def voteOnPost(postId:int, post:sch.VoteRequest=Body(...), db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    if post.post_id != postId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path postId and request post_id must match")
    # search for the post he wants to vote on against the db 
    # to firstly check whether that particular post is present or not in the db
    result=await db.execute(select(models.Post).where(models.Post.id==post.post_id))
    queriedPost=result.scalars().first()
    # if not present just raise an 404 error
    if not queriedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {post.post_id} not Found")
    # if present in db then search in the votes table for knowing if he has
    # already voted on the post or not
    voteResult=await db.execute(select(models.Votes).where(and_(models.Votes.post_id==post.post_id,models.Votes.user_id==currentUser.id)))
    currentVote=voteResult.scalars().first()
    try:
        # if currentVote is not None then record of voting exists
        # by that particular user in the votes table
        if currentVote:
            # User already voted, with the same choice
            if currentVote.action == post.choice:
                # Same choice again means remove the vote
                await db.delete(currentVote)
                await db.commit()
                # Fetch updated counts instead of refreshing entire object
                count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
                likes, dislikes = count_result.first()
                await delete_cache_pattern(f"post:{post.post_id}:*")
                # Use versioned cache keys instead of global feed:* invalidation (always enabled).
                await increment_cache_version("feed:home")
                await increment_cache_version("feed:explore")
                return sch.VoteResponse(message="Vote removed successfully", likes=likes, dislikes=dislikes)
            else:
                # Switching vote (e.g., like to dislike or vice versa)
                currentVote.action = post.choice
                await db.commit()
                # Fetch updated counts instead of refreshing entire object
                count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
                likes, dislikes = count_result.first()
                await delete_cache_pattern(f"post:{post.post_id}:*")
                # Use versioned cache keys instead of global feed:* invalidation (always enabled).
                await increment_cache_version("feed:home")
                await increment_cache_version("feed:explore")
                return sch.VoteResponse(message="Vote switched successfully", likes=likes, dislikes=dislikes)
        else:
            # New vote
            newVote = models.Votes(
                post_id=post.post_id,
                user_id=currentUser.id,
                action=post.choice
            )
            db.add(newVote)
            await db.commit()
            # Fetch updated counts instead of refreshing entire object
            count_result = await db.execute(select(models.Post.likes, models.Post.dis_likes).where(models.Post.id==post.post_id))
            likes, dislikes = count_result.first()
            await delete_cache_pattern(f"post:{post.post_id}:*")
            # Use versioned cache keys instead of global feed:* invalidation (always enabled).
            await increment_cache_version("feed:home")
            await increment_cache_version("feed:explore")
            # Notify the post owner when someone LIKES their post.
            # Only on new likes (not dislikes, not removals, not self-likes).
            if post.choice and currentUser.id != queriedPost.user_id:
                create_notification_task.delay(
                    actor_id=currentUser.id,
                    owner_id=queriedPost.user_id,
                    notif_type=NotificationType.like.value,
                    actor_username=currentUser.username,
                    entity_id=post.post_id,
                    entity_type="post",
                )
            return sch.VoteResponse(message="New vote added successfully", likes=likes, dislikes=dislikes)
    # triggers if any thing goes wrong in db as the logic is solid
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again"
                            )
@router.post("/comments/{commentId}/votes", status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
async def likeAComment(commentId:int, comment:sch.CommentVoteRequest=Body(...), db:AsyncSession=Depends(getDb), currentUser:models.User=Depends(oauth2.getCurrentUser)):
    if comment.comment_id != commentId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path commentId and request comment_id must match")
    # search for the comment he wants to vote on against the db 
    # to firstly check whether that particular comment is present or not in the db
    result=await db.execute(select(models.Comments).where(models.Comments.id==comment.comment_id))
    queriedComment=result.scalars().first()
    # if not present just raise an 404 error
    if not queriedComment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {comment.comment_id} not Found")
    # if present in db then search in the Commentvotes table for knowing if he has
    # already voted on the comment or not
    voteResult=await db.execute(select(models.CommentVotes).where(and_(models.CommentVotes.comment_id==comment.comment_id,models.CommentVotes.user_id==currentUser.id)))
    currentVote=voteResult.scalars().first()
    try:
        # if currentVote is not None then record of voting exists
        # by that particular user in the Commentvotes table
        if currentVote:
            # User already voted, with the same choice
            if currentVote.like==comment.choice:
                # Same choice again means remove the vote
                await db.delete(currentVote)
                await db.commit()
                # Fetch updated count instead of refreshing entire object
                count_result = await db.execute(select(models.Comments.likes).where(models.Comments.id==comment.comment_id))
                likes = count_result.scalar()
                return sch.VoteResponse(message="Vote removed successfully", likes=likes)
        else:
            # New like on a comment
            newVote=models.CommentVotes(
                comment_id=comment.comment_id,
                user_id=currentUser.id,
                like=comment.choice
            )
            db.add(newVote)
            await db.commit()
            # Fetch updated count instead of refreshing entire object
            count_result = await db.execute(select(models.Comments.likes).where(models.Comments.id==comment.comment_id))
            likes = count_result.scalar()
            return sch.VoteResponse(message="New vote added successfully", likes=likes)
    # triggers if any thing goes wrong in db as the logic is solid
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
