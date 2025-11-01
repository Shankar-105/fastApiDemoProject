from fastapi import APIRouter, Depends, HTTPException,Body  # Router = group endpoints, Depends = get DB, HTTPException = error msg
from sqlalchemy.orm import Session  # For DB talk
 # For random OTP
from app import models, utils, schemas,db,oauth2,otpstorage,email

router = APIRouter(tags=["ForgotPassword"])  # All URLs start with /auth

@router.post("/forgot-password")
async def forgot_password(db: Session = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Find user in DB    
    # Make random OTP (6 digits)
    otp=otpstorage.generateOtp()
    otpstorage.saveOtp(db,currentUser.email,otp)
    # Send email
    try:
       await email.send_otp_email(currentUser.email,otp)  # Use your email.py
    except:
        raise HTTPException(status_code=500, detail="Email send failed")  # Error if email breaks
    
    return {"message": "OTP sent to your email! Check inbox"}

def verifyOtp(db:Session,otp:str,currentUser:models.User):
    # Check if OTP good
    if otpstorage.checkOtp(db,currentUser.email,otp):
        return
    raise HTTPException(status_code=400, detail="Wrong or expired OTP")

@router.post("/reset-password")
def reset_password(request:schemas.ResetPassword=Body(...),db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # First, check OTP
    verifyOtp(db,request.otp,currentUser)
    # Hash new password (using your utils.py)
    currentUser.password = utils.hashPassword(request.new_password)
    # Save to DB
    db.commit()
    return {"message": "Password changed! Now login with new one."}