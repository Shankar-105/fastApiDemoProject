from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.orm import Session
import app.utils as utils
import os
router=APIRouter(
    tags=['Users']
)
@router.get("/users/{user_id}/profile",status_code=status.HTTP_200_OK,response_model=sch.UserProfile)
def userProfile(user_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    user=db.query(models.User).filter(models.User.id==user_id).first()
    userProfile=sch.UserProfile(
        profilePicture=user.profile_picture,
        username=user.username,
        nickname=user.nickname,
        bio=user.bio,
        posts=len(user.posts),
        followers=user.followers_cnt,
        following=user.following_cnt,
    )
    if not userProfile.bio:
        userProfile.bio=""
    if not userProfile.profilePicture:
        userProfile.profilePicture="no profile picture"
    return userProfile

@router.get("/users/{user_id}/profile/pic",status_code=status.HTTP_200_OK)
def myProfilePicture(user_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # get the curretn users profile pic
    user=db.query(models.User).filter(models.User.id==user_id).first()
    profilePicturePath = user.profile_picture
    # if he doesnt have a porfile pic return 404
    if not profilePicturePath:
        raise HTTPException(status_code=404, detail="No profile picture")
    file_path=f"profilepics/{profilePicturePath}"
    # optional check
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    # return a FileResponse class response to view it directly
    # as in commit hash <96bd0a3> or else return the link and you can
    # view it in the broswer by entering the output url
    return sch.UserProfileDisplay.displayUserProfilePic(user)

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
