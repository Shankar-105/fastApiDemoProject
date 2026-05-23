from datetime import datetime, timedelta  # For time stuff
import hashlib
import secrets
import random
import structlog

from app import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete


logger = structlog.get_logger(__name__)


def _hash_otp(raw_otp: str) -> str:
    return hashlib.sha256(raw_otp.encode("utf-8")).hexdigest()

def generateOtp():
    otp = str(random.randint(100000, 999999))
    logger.debug("otp_generated")
    return otp

async def saveOtp(db:AsyncSession,email:str,otp:str,minutes:int=2):
    logger.info("otp_saving", email=email, minutes=minutes)
    # remove any other expired otp's of the user if any
    await db.execute(delete(models.OTP).where(models.OTP.email == email))
    # calculate the expire time from now + 2 mins
    expire_time = datetime.now() + timedelta(minutes=minutes)
    # create an object to store
    currOtp=models.OTP(email=email,otp=_hash_otp(otp),expires_at=expire_time)
    # save the info to the otps table in db 
    db.add(currOtp)
    # commit the changes 
    await db.commit()
    await db.refresh(currOtp)

async def checkOtp(db:AsyncSession,email:str,user_otp:str) -> bool:
    logger.debug("otp_checking", email=email)
    # check for the otp_record for the email
    result=await db.execute(select(models.OTP).where(models.OTP.email==email))
    otp_record=result.scalars().first()
    # if not present return false indicating wrong otp
    if not otp_record:
        logger.warning("otp_check_failed_not_found", email=email)
        return False 
    # if expired return false indicating wrong otp
    if datetime.now() > otp_record.expires_at:
        # and remove the old one
        await db.delete(otp_record)
        await db.commit()
        logger.warning("otp_check_failed_expired", email=email)
        return False
    # verify the otp
    if otp_record.otp == _hash_otp(user_otp):
        logger.info("otp_check_success", email=email)
        # remove the otp after successfull check
        await db.delete(otp_record)
        await db.commit()
        return True
    logger.warning("otp_check_failed_invalid", email=email)
    return False
    # if matches?
    if secrets.compare_digest(otp_record.otp, _hash_otp(user_otp)):
        # remove it and return true indicating correct otp
        await db.delete(otp_record)
        await db.commit()
        logger.info("OTP validated successfully", extra={"extra_info": {"email": email}})
        return True
    logger.warning("OTP check failed: mismatch", extra={"extra_info": {"email": email}})
    return False  # or else wrong otp
