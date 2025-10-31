from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.orm import Session
import app.utils as utils

router=APIRouter(
    tags=['Users']
)

@router.post("/user/signup",status_code=status.HTTP_201_CREATED,response_model=sch.UserResponse)
def createUser(userData:sch.UserEssentials=Body(...),db:Session=Depends(db.getDb)):
    # hash the password using the bcrypt lib
    hashedPw=utils.hashPassword(userData.password)
    userData.password=hashedPw
    newUser=models.User(**userData.dict())
    db.add(newUser)
    db.commit()
    db.refresh(newUser)
    return newUser

@router.get("/users/getAllUsers",status_code=status.HTTP_201_CREATED,response_model=List[sch.UserResponse])
def getAllUsers(db:Session=Depends(db.getDb)):
    allUsers=db.query(models.User).all()
    return allUsers

@router.get("/users/{user_id}/followers",status_code=status.HTTP_200_OK)
def get_followers(user_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    return {f"{user.username}'s followers":[{"id": follower.id, "username": follower.username} for follower in user.followers]}

@router.get("/users/{user_id}/following",status_code=status.HTTP_200_OK)
def get_following(user_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404,detail="User not found")
    return {f"{user.username} is following":[{"id": follower.id, "username": follower.username} for follower in user.following]}

@router.get("/users/{user_id}/posts",response_model=List[sch.PostResponse])  
def getAllPosts(user_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
   # allPosts=db.query(models.Post).filter(models.Post.user_id==currentUser.id).all()
   # simple way of querying 
   # Thanks to the relationship() method 
    user=db.query(models.User).filter(models.User.id==user_id).first()
    allPosts=user.posts
    return allPosts
