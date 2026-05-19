from fastapi import status,HTTPException,Depends,Body,APIRouter
from app import db,models,oauth2
from app.services import token_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.utils import thread_helpers as utils
import app.schemas as sch
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from datetime import datetime, timezone
import app.services.redis_service as redis_service
import app.services.otp_service as otp_service
import app.services.email_service as email_service
from app.config import settings as cg
from sqlalchemy.orm.exc import StaleDataError
from app.services.concurrency_service import lock_user_row, run_with_transient_retry
from app.services.rate_limit_service import login_limiter, forgot_password_limiter, reset_password_limiter, refresh_limiter
from app.tasks.email_tasks import send_otp_email as send_otp_email_task
from app.tasks.email_tasks import send_verification_email as send_verification_email_task
import logging

router=APIRouter(
    prefix="/auth",
    tags=['Authentication']
)

logger = logging.getLogger("app")

@router.post("/login",status_code=status.HTTP_202_ACCEPTED)
async def loginUser(userCred:OAuth2PasswordRequestForm=Depends(),db:AsyncSession=Depends(db.getDb),_:None=Depends(login_limiter)):
    logger.info(f"Login attempt for username: {userCred.username}")
    result = await db.execute(select(models.User).where(models.User.username == userCred.username))
    isUserPresent = result.scalars().first()
    if not isUserPresent:
        logger.warning(f"Login failed for username: {userCred.username} - user not found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not await utils.verifyPassword(userCred.password, isUserPresent.password):
        logger.warning(f"Login failed for username: {userCred.username} - invalid password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not isUserPresent.email_verified:
        logger.warning(f"Login failed for username: {userCred.username} - email not verified")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
    tokenData = {"userId": isUserPresent.id, "userName": isUserPresent.username}
    access_token = await oauth2.createAccessToken(tokenData)
    await redis_service.set_cache(
        f"auth:user:{access_token}",
        {
            "id": isUserPresent.id,
            "username": isUserPresent.username,
            "nickname": isUserPresent.nickname,
            "bio": isUserPresent.bio,
            "email": isUserPresent.email,
            "email_verified": isUserPresent.email_verified,
            "profile_picture": isUserPresent.profile_picture,
            "created_at": isUserPresent.created_at.isoformat() if isUserPresent.created_at else None,
            "followers_cnt": isUserPresent.followers_cnt,
            "following_cnt": isUserPresent.following_cnt,
        },
        ttl=cg.access_token_expire_time * 60,
    )
    refresh_token = await token_service.create_refresh_token(db, isUserPresent.id)
    logger.info(f"Login successful for username: {userCred.username}, user_id: {isUserPresent.id}")
    return sch.TokenModel(
        id=isUserPresent.id,
        username=isUserPresent.username,
        accessToken=access_token,
        refreshToken=refresh_token,
        tokenType="bearer"
    )

@router.post("/refresh-token", status_code=status.HTTP_200_OK)
async def refresh_token(payload: sch.RefreshTokenRequest = Body(...), db: AsyncSession = Depends(db.getDb), _: None = Depends(refresh_limiter)):
    logger.info("Token refresh attempt")
    access_token, new_refresh = await token_service.rotate_refresh_token(db, payload.refresh_token)
    logger.info("Token refresh successful")
    return {"accessToken": access_token, "refreshToken": new_refresh}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(token: str = Depends(oauth2.oauth2_scheme), db: AsyncSession = Depends(db.getDb)):
    logger.info("Logout attempt")
    try:
        payload = await oauth2.decodeToken(token)
        user_id = payload.get("userId")
        
        await redis_service.delete_cache(f"auth:user:{token}")
        
        payload = await oauth2.decodeToken(token)
        expire_time = payload.get("expTime")
        if expire_time:
            remaining_time = expire_time - datetime.now(timezone.utc).timestamp()
            if remaining_time > 0:
                await redis_service.add_to_blacklist(token, int(remaining_time))
        if user_id:
            await token_service.revoke_all_user_tokens(db, user_id)
        logger.info(f"Logout successful for user_id: {user_id}")
        return {"message": "Successfully logged out"}
    except JWTError:
        logger.warning("Logout failed - invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

@router.post("/password/forgot", status_code=status.HTTP_200_OK)
async def forgot_password(payload: sch.ForgotPasswordSchema, db: AsyncSession = Depends(db.getDb), _: None = Depends(forgot_password_limiter)):
    logger.info(f"Forgot password request for email: {payload.email}")
    result = await db.execute(select(models.User).where(models.User.email == payload.email))
    user = result.scalars().first()
    if not user:
        logger.info(f"Forgot password request for non-existent email: {payload.email}")
        return {"message": "If an account with this email exists, an OTP has been sent."}

    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, payload.email, otp, minutes=5)

    send_otp_email_task.delay(to_email=payload.email, otp=otp)
    logger.info(f"OTP sent for password reset to email: {payload.email}")
    return {"message": "If an account with this email exists, an OTP has been sent."}

@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(payload: sch.ResetPasswordSchema, db: AsyncSession = Depends(db.getDb), _: None = Depends(reset_password_limiter)):
    logger.info(f"Password reset attempt for email: {payload.email}")
    if not await otp_service.checkOtp(db, payload.email, payload.otp):
        logger.warning(f"Password reset failed for email: {payload.email} - invalid or expired OTP")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP."
        )

    async def _reset_password():
        user = await lock_user_row(db, email=payload.email)
        hashed_password = await utils.hashPassword(payload.new_password)
        user.password = hashed_password
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            logger.warning(f"Password reset conflict for email: {payload.email} - concurrent update")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Password was updated concurrently")
        return user

    await run_with_transient_retry(lambda: _reset_password(), db=db)
    logger.info(f"Password reset successful for email: {payload.email}")
    return {"message": "Password has been reset successfully."}


@router.post("/email/verify", status_code=status.HTTP_200_OK)
async def verify_email(payload: sch.VerifyEmailRequest, db: AsyncSession = Depends(db.getDb)):
    logger.info(f"Email verification attempt for email: {payload.email}")
    async def _verify_email():
        user = await lock_user_row(db, email=payload.email)
        if user.email_verified:
            await db.rollback()
            logger.info(f"Email already verified: {payload.email}")
            return {"message": "Email already verified"}

        ok = await otp_service.checkOtp(db, payload.email, payload.otp)
        if not ok:
            await db.rollback()
            logger.warning(f"Email verification failed for: {payload.email} - invalid or expired OTP")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

        user.email_verified = True
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            logger.warning(f"Email verification conflict for: {payload.email} - concurrent update")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email verification was updated concurrently")
        return {"message": "Email verified successfully"}

    result = await run_with_transient_retry(lambda: _verify_email(), db=db)
    logger.info(f"Email verified successfully: {payload.email}")
    return result


@router.post("/email/resend-otp", status_code=status.HTTP_200_OK)
async def resend_verification_otp(payload: sch.ResendVerificationOtpRequest, db: AsyncSession = Depends(db.getDb), _: None = Depends(forgot_password_limiter)):
    logger.info(f"Resend verification OTP request for email: {payload.email}")
    result = await db.execute(select(models.User).where(models.User.email == payload.email))
    user = result.scalars().first()
    if not user:
        logger.info(f"Resend OTP request for non-existent email: {payload.email}")
        return {"message": "If an account with this email exists, an OTP has been sent."}

    if user.email_verified:
        logger.info(f"Email already verified, skipping OTP for: {payload.email}")
        return {"message": "Email already verified"}

    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, payload.email, otp, minutes=5)
    
    send_verification_email_task.delay(to_email=payload.email, otp=otp)
    logger.info(f"Verification OTP resent to: {payload.email}")
    return {"message": "Verification OTP sent to your email."}



