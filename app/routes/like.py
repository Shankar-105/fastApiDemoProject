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

@router.post("/like",status_code=status.HTTP_201_CREATED)
def like(post:sch.LikeModel=Body(...),db:Session=Depends(getDb),currentUser:sch.TokenModel=Depends(oauth2.getCurrentUser)):
    queriedPost=db.query(models.Post).filter(models.Post.id==post.postId).first()
    if not queriedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {post.postId} not Found")
    # doesPostExist=db.query(models.Likes).filter(and_(models.Likes.postId==post.postId,models.Likes.postId==currentUser.id)).first()
    newVote=models.Likes(
        postId=post.postId,
        userId=currentUser.id,
        action=post.choice
    )
    try:
        # Add it to the session and commit
        db.add(newVote)
        if post.choice:
            queriedPost.likes += 1
        else:
            queriedPost.disLikes += 1
        db.commit()
    except IntegrityError:
        # This catches the duplicate key error if the check above fails
        db.rollback()  # Rollback the transaction
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already voted on this post")
    db.refresh(queriedPost)
    return {"status":"vote successfully added"}