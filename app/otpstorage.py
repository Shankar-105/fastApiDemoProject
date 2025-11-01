from datetime import datetime, timedelta  # For time stuff
from app import models,db
from sqlalchemy.orm import Session
import random 
def generateOtp():
    otp = str(random.randint(100000, 999999))
    return otp
def saveOtp(db:Session,email:str,otp:str,minutes:int=2):
    # Save OTP with expire time
    db.query(models.OTP).filter(models.OTP.email == email).delete()
    expire_time = datetime.now() + timedelta(minutes=minutes)  # Now + 2 min
    currOtp=models.OTP(email=email,otp=otp,expires_at=expire_time)
    db.add(currOtp)
    db.commit()
    db.refresh(currOtp)

def checkOtp(db:Session,email:str,user_otp:str) -> bool:
    # Get from box
    otp_record=db.query(models.OTP).filter(models.OTP.email==email).first()
    print(otp_record.email)
    print(otp_record.otp)
    print(user_otp)
    if not otp_record:
        print("doesnt exist????")
        return False  # No OTP
    # Expired?
    if datetime.now() > otp_record.expires_at:
        print("expired????")
        # Remove old one
        db.delete(otp_record)
        db.commit()
        return False
    # Match?
    if otp_record.otp == user_otp:
        print("are youu equal???")
        db.delete(otp_record)
        db.commit()
        return True
    return False  # Wrong OTP