from fastapi import status,HTTPException,Depends,Body,APIRouter,BackgroundTasks
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
from sqlalchemy.exc import IntegrityError
from app.services.notification_service import create_notification
from app.models import NotificationType
from app.services.redis_service import delete_cache_pattern

router=APIRouter(
    tags=['likes']
)

@router.post("/vote/on_post",status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
# get the post user that user wants to vote on with which user he is
async def voteOnPost(post:sch.VoteRequest=Body(...),db:AsyncSession=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser),background_tasks:BackgroundTasks=BackgroundTasks()):
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
                # update the same on the posts table also
                # by removing the vote accordingly (like/dislike)
                if post.choice:
                    queriedPost.likes -= 1
                else:
                    queriedPost.dis_likes-= 1
                await db.commit()
                await db.refresh(queriedPost)
                await delete_cache_pattern(f"post:{post.post_id}:*")
                await delete_cache_pattern("feed:*")
                return sch.VoteResponse(message="Vote removed successfully", likes=queriedPost.likes, dislikes=queriedPost.dis_likes)
            else:
                # Switching vote (e.g., like to dislike or vice versa)
                currentVote.action = post.choice
                if post.choice:
                    queriedPost.likes += 1
                    queriedPost.dis_likes -= 1
                else:
                    queriedPost.likes -= 1
                    queriedPost.dis_likes += 1
                await db.commit()
                await db.refresh(queriedPost)
                await delete_cache_pattern(f"post:{post.post_id}:*")
                await delete_cache_pattern("feed:*")
                return sch.VoteResponse(message="Vote switched successfully", likes=queriedPost.likes, dislikes=queriedPost.dis_likes)
        else:
            # New vote
            newVote = models.Votes(
                post_id=post.post_id,
                user_id=currentUser.id,
                action=post.choice
            )
            db.add(newVote)
            # if user choice is true increase likes count
            if post.choice:
                queriedPost.likes += 1
            # or else dilikes count
            else:
                queriedPost.dis_likes += 1
            await db.commit()
            await db.refresh(queriedPost)
            await delete_cache_pattern(f"post:{post.post_id}:*")
            await delete_cache_pattern("feed:*")
            # Notify the post owner when someone LIKES their post.
            # Only on new likes (not dislikes, not removals, not self-likes).
            if post.choice and currentUser.id != queriedPost.user_id:
                background_tasks.add_task(
                    create_notification,
                    actor_id=currentUser.id,
                    owner_id=queriedPost.user_id,
                    notif_type=NotificationType.like,
                    actor_username=currentUser.username,
                    entity_id=post.post_id,
                    entity_type="post",
                )
            return sch.VoteResponse(message="New vote added successfully", likes=queriedPost.likes, dislikes=queriedPost.dis_likes)
    # triggers if any thing goes wrong in db as the logic is solid
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again"
                            )
@router.post("/vote/on_comment",status_code=status.HTTP_201_CREATED, response_model=sch.VoteResponse)
async def likeAComment(comment:sch.CommentVoteRequest=Body(...),db:AsyncSession=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
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
                # update the same on the CommentVotes table also
                # by removing the vote (like)
                if comment.choice:
                    queriedComment.likes-=1
                await db.commit()
                await db.refresh(queriedComment)
                return sch.VoteResponse(message="Vote removed successfully", likes=queriedComment.likes)
        else:
            # New like on a comment
            newVote=models.CommentVotes(
                comment_id=comment.comment_id,
                user_id=currentUser.id,
                like=comment.choice
            )
            db.add(newVote)
            # if user choice is true increase likes count
            if comment.choice:
                queriedComment.likes+=1
            await db.commit()
            await db.refresh(queriedComment)
            return sch.VoteResponse(message="New vote added successfully", likes=queriedComment.likes)
    # triggers if any thing goes wrong in db as the logic is solid
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")
