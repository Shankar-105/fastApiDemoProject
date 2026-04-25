from fastapi import APIRouter, Depends, HTTPException,Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models,schemas,db,oauth2
from app.services import email_service, otp_service, token_service
from app.my_utils import utils
from sqlalchemy.orm.exc import StaleDataError
from app.services.concurrency_service import lock_user_row, run_with_transient_retry
from app.rate_limiter import change_password_limiter, reset_password_auth_limiter

router = APIRouter(tags=["changepassword"])

@router.post("/change-password", response_model=schemas.SuccessResponse)
async def change_password(db: AsyncSession = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser),_:None=Depends(change_password_limiter)):
    # call the generate otp method in the otp_service file which generates an otp
    otp=otp_service.generateOtp()
    # save this otp in the db using the saveOtp method in the otp_sevice file 
    await otp_service.saveOtp(db,currentUser.email,otp)
    # after storing it in the db Send email using the method in email file
    try:
       await email_service.send_otp_email(currentUser.email,otp) 
    except:
        # if any probelm their raise an exception
        raise HTTPException(status_code=500, detail="Email send failed") 
    return schemas.SuccessResponse(message="OTP sent to your email! Check inbox")

async def verifyOtp(db:AsyncSession,otp:str,currentUser:models.User):
    # Check if OTP good
    if await otp_service.checkOtp(db,currentUser.email,otp):
        return
    await db.rollback()
    raise HTTPException(status_code=400,detail="Wrong or expired OTP")

@router.post("/reset-password-auth", response_model=schemas.SuccessResponse)
async def reset_password(request:schemas.PasswordResetRequest=Body(...),db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser),_:None=Depends(reset_password_auth_limiter)):
    async def _reset_password():
        locked_user = await lock_user_row(db, user_id=currentUser.id)
        # first check whether the user entered the correct current password
        if not await utils.verifyPassword(request.old_password, locked_user.password):
            await db.rollback()
            raise HTTPException(status_code=403,detail="your old password is incorrect")
        # then, check if it is a valid otp before letting user change password
        await verifyOtp(db,request.otp,locked_user)
        # Hash new password (offloaded to thread pool)
        locked_user.password = await utils.hashPassword(request.new_password)
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Password was updated concurrently")

    await run_with_transient_retry(lambda: _reset_password(), db=db)
    # Revoke all refresh tokens — forces re-login on every device
    await token_service.revoke_all_user_tokens(db, currentUser.id)
    return schemas.SuccessResponse(message="Password changed successfully! Now login with new one.")