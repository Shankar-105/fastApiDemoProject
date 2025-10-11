from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models
from app import db
from sqlalchemy.orm import Session
import app.utils as utils
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