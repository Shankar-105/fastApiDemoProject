from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models
from app.db import getDb
from sqlalchemy.orm import Session
import app.utils as utils
router=APIRouter(
    tags=['Users']
)

@router.post("/user/signup",status_code=status.HTTP_201_CREATED,response_model=sch.UserResponse)
def createUser(userData:sch.UserEssentials=Body(...),db:Session=Depends(getDb)):
    hashedPw=utils.hashPassword(userData.password)
    userData.password=hashedPw
    new_user=models.User(**userData.dict())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
@router.get("/user/getAllUsers",status_code=status.HTTP_201_CREATED,response_model=List[sch.UserResponse])
def getAllUsers(db:Session=Depends(getDb)):
    allUsers=db.query(models.User).all()
    return allUsers