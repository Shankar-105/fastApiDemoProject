from fastapi import status,HTTPException,Depends,Body,APIRouter
from app import db,models,oauth2
from sqlalchemy.orm import Session
import app.utils as utils
import app.schemas as sch


router=APIRouter(tags=['Authentication'])
@router.post("/login",status_code=status.HTTP_202_ACCEPTED)
# method which log's in user if he has an account
def loginUser(userCred:sch.UserLoginCred=Body(...),db:Session=Depends(db.getDb)):
  # checks against the db for the username provided 
  isUserPresent=db.query(models.User).filter(models.User.username==userCred.username).first()
  # if not found tell the user not found
  if not isUserPresent:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"user {userCred.username} not Found")
  # if found but he entered a wrong password tell him 
  if not utils.verifyPassword(userCred.password,isUserPresent.password):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"incorrect password")
  # if both username and password verfication is successfull call
  # the createAccessToken from oauth2 file which generates an jwt token
  accessToken=oauth2.createAccessToken({"userId":isUserPresent.id,"userName":isUserPresent.username})
  # return the access token
  return {"access_token":accessToken,"token_type":"bearer"}

 