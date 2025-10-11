from fastapi import status,HTTPException,Depends,Body,APIRouter
from app import db,models,oauth2
from sqlalchemy.orm import Session
import app.utils as utils
import app.schemas as sch


router=APIRouter(tags=['Authentication'])
@router.post("/login",status_code=status.HTTP_202_ACCEPTED)
def loginUser(userCred:sch.UserLoginCred=Body(...),db:Session=Depends(db.getDb)):
  isUserPresent=db.query(models.User).filter(models.User.username==userCred.username).first()

  if not isUserPresent:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"user {userCred.username} not Found")
  if not utils.verifyPassword(userCred.password,isUserPresent.password):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"incorrect password")
  
  accessToken=oauth2.createAccessToken({"userId":isUserPresent.id,"userName":isUserPresent.username})
  return {"access_token":accessToken,"token_type":"bearer"}

 