from fastapi import APIRouter, Depends, HTTPException,Body
from sqlalchemy.orm import Session 
from app import models, otp_service, utils, schemas,db,oauth2,email

router = APIRouter(tags=["ForgotPassword"])

@router.post("/forgot-password")
async def forgot_password(db: Session = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # call the generate otp method in the otp_service file which generates an otp
    otp=otp_service.generateOtp()
    # save this otp in the db using the saveOtp method in the otp_sevice file 
    otp_service.saveOtp(db,currentUser.email,otp)
    # after storing it in the db Send email using the method in email file
    try:
       await email.send_otp_email(currentUser.email,otp) 
    except:
        # if any probelm their raise an exception
        raise HTTPException(status_code=500, detail="Email send failed") 
    return {"message": "OTP sent to your email! Check inbox"}

def verifyOtp(db:Session,otp:str,currentUser:models.User):
    # Check if OTP good
    if otp_service.checkOtp(db,currentUser.email,otp):
        return
    raise HTTPException(status_code=400, detail="Wrong or expired OTP")

@router.post("/reset-password")
def reset_password(request:schemas.ResetPassword=Body(...),db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # first, check if it is a valid otp before letting user change password
    verifyOtp(db,request.otp,currentUser)
    # Hash new password (using methods in utils.py)
    currentUser.password = utils.hashPassword(request.new_password)
    # Save to DB
    db.commit()
    return {"message": "Password changed! Now login with new one."}