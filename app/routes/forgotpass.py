from fastapi import APIRouter, Depends, HTTPException  # Router = group endpoints, Depends = get DB, HTTPException = error msg
from sqlalchemy.orm import Session  # For DB talk
import random  # For random OTP
from app import models, utils, schemas,db, otp_store,config,oauth2  # Your stuff
from app.config import settings  # For email settings
import email

router = APIRouter(tags=["ForgotPassword"])  # All URLs start with /auth

@router.post("/forgot-password")
def forgot_password(db: Session = Depends(db.getDb),currenUser:models.User=Depends(oauth2.getCurrentUser)):
    # Find user in DB    
    # Make random OTP (6 digits)
    otp = str(random.randint(100000, 999999))  # Like 123456
    # Save in temp box
    otp_store.save_otp(currenUser.email, otp)
    # Send email
    try:
        email.send_otp_email(currenUser.email, otp)  # Use your email.py
    except:
        raise HTTPException(status_code=500, detail="Email send failed")  # Error if email breaks
    
    return {"message": "OTP sent to your email! Check inbox."}

def verify_otp(otp:str,currenUser:models.User=Depends(oauth2.getCurrentUser)):
    # Check if OTP good
    if otp_store.check_otp(currenUser.email,otp):
        return {"message": "OTP is correct!"}
    raise HTTPException(status_code=400, detail="Wrong or expired OTP")

@router.post("/reset-password")
def reset_password(request: schemas.ResetPassword, db: Session = Depends(db.getDb),currenUser:models.User=Depends(oauth2.getCurrentUser)):
    # First, check OTP
    verify_otp(request.otp)
    # Hash new password (using your utils.py)
    currenUser.password = utils.hashPassword(request.new_password)
    # Save to DB
    db.commit()
    return {"message": "Password changed! Now login with new one."}