from fastapi import status,HTTPException,Depends,Body,APIRouter,Form
from typing import List
import app.schemas as sch
from app import models,db,oauth2
from sqlalchemy.orm import Session
import app.utils as utils
import os,shutil
from fastapi import UploadFile,File
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

@router.get("/user/getAllUsers",status_code=status.HTTP_201_CREATED,response_model=List[sch.UserResponse])
def getAllUsers(db:Session=Depends(db.getDb)):
    allUsers=db.query(models.User).all()
    return allUsers
# a patch endpoint so that user can update what he wants to unlike put
# profile picture cannot be taken as a json data so it must be passed via Form
# and the username and bio can be passed via Body params but its resulting in an
# ambiguity as one of the section is being passed via Form and the other via Body
# so made everything to be passed via Form only
@router.patch("/user/updateInfo",status_code=status.HTTP_200_OK)
def updateUserInfo(username:str=Form(None),bio:str=Form(None),profile_picture:UploadFile=File(None),db:Session=Depends(db.getDb),currentUser:sch.TokenModel=Depends(oauth2.getCurrentUser)):
    # to store updates the user does
    updates={}
    if username:
        if db.query(models.User).filter(models.User.username == username,models.User.id !=currentUser.id).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        updates["username"] = username
    if bio:
        updates['bio']=bio
    if profile_picture:
        # creating an profilepics directory to store the
        # users profile pics locally instead of inserting them
        # into the db which is a bad practice
        os.makedirs("profilepics", exist_ok=True)
        # allowing only certain file types
        # File.content_type method returns image/extension if its not
        # present in our list we raise an error
        allowedFileTypes=['image/jpeg','image/png','image/gif']
        if profile_picture.content_type not in allowedFileTypes:
            raise HTTPException(status_code=400,detail="only jpeg,png,gif files allowed")
        # if not we create a filePath to store this path in the db 
        # instead of directly storing the image itself
        file_path=f"profilepics/{currentUser.username}_{profile_picture.filename}"
        # py methods to copy the argumented image in our filepath
        with open(file_path, "wb") as buffer:
           shutil.copyfileobj(profile_picture.file, buffer)
        updates['profile_picture']=file_path
        # if any updates update them
    if updates:
        db.query(models.User).filter(models.User.id==currentUser.id).update(updates)
        db.commit()
        db.refresh(currentUser)
    return updates
