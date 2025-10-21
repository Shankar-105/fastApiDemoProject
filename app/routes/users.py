from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.orm import Session
import app.utils as utils
import os,shutil
router=APIRouter(
    tags=['Users']
)

@router.post("/user/signup",status_code=status.HTTP_201_CREATED,response_model=sch.UserResponse)
def createUser(userData:sch.UserEssentials=Body(...),db:Session=Depends(db.getDb)):
    hashedPw=utils.hashPassword(userData.password)
    userData.password=hashedPw
    newUser=models.User(**userData.dict())
    db.add(newUser)
    db.commit()
    db.refresh(newUser)
    return newUser

@router.get("/user/getAllUsers",status_code=status.HTTP_201_CREATED,response_model=List[sch.UserResponse])
def getAllUsers(db:Session=Depends(db.getDb)):
    allUsers=db.query(models.User).all()
    return allUsers

@router.patch("/user/updateInfo",status_code=status.HTTP_201_CREATED)
def updateUserInfo(updateInfo:sch.UserUpdateInfo=Body(...),db:Session=Depends(db.getDb),currentUser:sch.TokenModel=Depends(oauth2.getCurrentUser)):
    updates={}
    if updateInfo.username:
        if db.query(models.User).filter(models.User.username == updateInfo.username,models.User.id !=currentUser.id).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        updates["username"] = updateInfo.username
    if updateInfo.bio:
        updates['bio']=updateInfo.bio
    if updates:
        db.query(models.User).filter(models.User.id==currentUser.id).update(updates)
        db.commit()
        db.refresh(currentUser)
    return updates
