from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models
from app.db import getDb
from sqlalchemy.orm import Session

router=APIRouter()

@router.post("/user/signup",status_code=status.HTTP_201_CREATED,response_model=sch.UserResponse)
def createUser(newUser:sch.UserEssentials=Body(...),db:Session=Depends(getDb)):
    newUser=models.User(**newUser.dict())
    db.add(newUser)
    db.commit()
    db.refresh(newUser)
    return newUser
