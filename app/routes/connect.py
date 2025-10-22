from fastapi import status,HTTPException,Depends,Body,APIRouter
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

router=APIRouter(tags=['connections'])

@router.post("/connect/{user_id}",status_code=status.HTTP_201_CREATED)
def follow(user_id:int,db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    userToFollow=db.query(models.User).filter(models.User.id==user_id).first()
    if not userToFollow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User doesnt exist")
    if userToFollow.id == currentUser.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot follow yourself")
    if userToFollow in currentUser.following:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Your already following this user")
    try:
        currentUser.following.append(userToFollow)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to follow user")
    return {"message":f"followed user {userToFollow}"}
    