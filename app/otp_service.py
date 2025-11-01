from datetime import datetime, timedelta  # For time stuff
from app import models
from sqlalchemy.orm import Session
import random 
def generateOtp():
    otp = str(random.randint(100000, 999999))
    return otp

def saveOtp(db:Session,email:str,otp:str,minutes:int=2):
    # remove any other expired otp's of the user if any
    db.query(models.OTP).filter(models.OTP.email == email).delete()
    # calculate the expire time from now + 2 mins
    expire_time = datetime.now() + timedelta(minutes=minutes)
    # create an object to store
    currOtp=models.OTP(email=email,otp=otp,expires_at=expire_time)
    # save the info to the otps table in db 
    db.add(currOtp)
    # commit the changes 
    db.commit()
    db.refresh(currOtp)

def checkOtp(db:Session,email:str,user_otp:str) -> bool:
    # check for the otp_record for the email
    otp_record=db.query(models.OTP).filter(models.OTP.email==email).first()
    # if not present return false indicating wrong otp
    if not otp_record:
        return False 
    # if expired return false indicating wrong otp
    if datetime.now() > otp_record.expires_at:
        # and remove the old one
        db.delete(otp_record)
        db.commit()
        return False
    # if matches?
    if otp_record.otp == user_otp:
        # remove it and return true indicating correct otp
        db.delete(otp_record)
        db.commit()
        return True
    return False  # or else wrong otp