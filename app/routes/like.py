from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

router=APIRouter(
    tags=['likes']
)

@router.post("/vote",status_code=status.HTTP_201_CREATED)
# get the post user that user wants to vote on with which user he is
def vote(post:sch.VoteModel=Body(...),db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # search for the post he wants to vote on against the db 
    # to firstly check whether that particular post is present or not in the db
    queriedPost=db.query(models.Post).filter(models.Post.id==post.post_id).first()
    # if not present just raise an 404 error
    if not queriedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {post.post_id} not Found")
    # if present in db then search in the votes table for knowing if he has
    # already voted on the post or not
    currentVote=db.query(models.Votes).filter(and_(models.Votes.post_id==post.post_id,models.Votes.user_id==currentUser.id)).first()
    try:
        # if currentVote is not None then record of voting exists
        # by that particular user in the votes table
        if currentVote:
            # User already voted, with the same choice
            if currentVote.action == post.choice:
                # Same choice again means remove the vote
                db.delete(currentVote)
                # update the same on the posts table also
                # by removing the vote accordingly (like/dislike)
                if post.choice:
                    queriedPost.likes -= 1
                else:
                    queriedPost.disLikes -= 1
                db.commit()
                db.refresh(queriedPost)
                return {"message": "Vote removed successfully"}
            else:
                # Switching vote (e.g., like to dislike or vice versa)
                currentVote.action = post.choice
                if post.choice:
                    queriedPost.likes += 1
                    queriedPost.dis_likes -= 1
                else:
                    queriedPost.likes -= 1
                    queriedPost.dis_likes += 1
                db.commit()
                db.refresh(queriedPost)
                return {"message": "Vote switched successfully"}
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
            db.commit()
            db.refresh(queriedPost)
            return {"message": "New vote added successfully"}
    # triggers if any thing goes wrong in db as the logic is solid
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")