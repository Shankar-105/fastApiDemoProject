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
def vote(post:sch.VoteModel=Body(...),db:Session=Depends(getDb),currentUser:sch.TokenModel=Depends(oauth2.getCurrentUser)):
    queriedPost=db.query(models.Post).filter(models.Post.id==post.postId).first()
    if not queriedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {post.postId} not Found")
    currentVote=db.query(models.Likes).filter(and_(models.Likes.postId==post.postId,models.Likes.userId==currentUser.id)).first()
    try:
        if currentVote:
            # User already voted, handle toggle or removal
            if currentVote.action == post.choice:
                # Same choice again means remove the vote
                db.delete(currentVote)
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
                    queriedPost.disLikes -= 1
                else:
                    queriedPost.likes -= 1
                    queriedPost.disLikes += 1
                db.commit()
                db.refresh(queriedPost)
                return {"message": "Vote switched successfully"}
        else:
            # New vote
            newVote = models.Likes(
                postId=post.postId,
                userId=currentUser.id,
                action=post.choice
            )
            db.add(newVote)
            if post.choice:
                queriedPost.likes += 1
            else:
                queriedPost.disLikes += 1
            db.commit()
            db.refresh(queriedPost)
            return {"message": "New vote added successfully"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Database error, please try again")