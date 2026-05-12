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
from app.rate_limiter import login_limiter, forgot_password_limiter, reset_password_limiter, refresh_limiter
from app.tasks.email_tasks import send_otp_email as send_otp_email_task
from app.tasks.email_tasks import send_verification_email as send_verification_email_task

router=APIRouter(
    prefix="/v1/auth",
    tags=['Authentication']
)

@router.post("/login",status_code=status.HTTP_202_ACCEPTED)
# method which log's in user if he has an account
# using the built-in schema for login 'OAuth2PasswordRequestForm'
# which is equivalent to our 'sch.UserLoginCred'
async def loginUser(userCred:OAuth2PasswordRequestForm=Depends(),db:AsyncSession=Depends(db.getDb),_:None=Depends(login_limiter)):
    # checks against the db for the username provided
    result = await db.execute(select(models.User).where(models.User.username == userCred.username))
    isUserPresent = result.scalars().first()
    # if not found tell the user not found
    if not isUserPresent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # if found but he entered a wrong password tell him
    if not await utils.verifyPassword(userCred.password, isUserPresent.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not isUserPresent.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
    # if both username and password verfication is successfull call
    # the createAccessToken from oauth2 file which generates an jwt token
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
    # create a refresh token for this login session (new family)
    refresh_token = await token_service.create_refresh_token(db, isUserPresent.id)
    # return both tokens
    return sch.TokenModel(
        id=isUserPresent.id,
        username=isUserPresent.username,
        accessToken=access_token,
        refreshToken=refresh_token,
        tokenType="bearer"
    )

@router.post("/refresh-token", status_code=status.HTTP_200_OK)
async def refresh_token(payload: sch.RefreshTokenRequest = Body(...), db: AsyncSession = Depends(db.getDb), _: None = Depends(refresh_limiter)):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old refresh token is revoked (rotation).
    """
    access_token, new_refresh = await token_service.rotate_refresh_token(db, payload.refresh_token)
    return {"accessToken": access_token, "refreshToken": new_refresh}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(token: str = Depends(oauth2.oauth2_scheme), db: AsyncSession = Depends(db.getDb)):
    try:
        # Decode the token to get the user ID
        payload = await oauth2.decodeToken(token)
        user_id = payload.get("userId")
        
        # Invalidate user cache (use token as key to match oauth2.py)
        await redis_service.delete_cache(f"auth:user:{token}")
        
        # Decode the token to get the expiration time
        payload = await oauth2.decodeToken(token)
        expire_time = payload.get("expTime")
        if expire_time:
            # Calculate remaining time (use UTC to match token creation)
            remaining_time = expire_time - datetime.now(timezone.utc).timestamp()
            if remaining_time > 0:
                # Add token to blacklist with remaining time as TTL
                await redis_service.add_to_blacklist(token, int(remaining_time))
        # Also revoke all refresh tokens for this user so no
        # device can silently get new access tokens after logout.
        if user_id:
            await token_service.revoke_all_user_tokens(db, user_id)
        return {"message": "Successfully logged out"}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

@router.post("/password/forgot", status_code=status.HTTP_200_OK)
async def forgot_password(payload: sch.ForgotPasswordSchema, db: AsyncSession = Depends(db.getDb), _: None = Depends(forgot_password_limiter)):
    result = await db.execute(select(models.User).where(models.User.email == payload.email))
    user = result.scalars().first()
    if not user:
        # To prevent user enumeration, we don't reveal if the user exists or not.
        # We'll just return a success message.
        return {"message": "If an account with this email exists, an OTP has been sent."}

    # Generate and save OTP
    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, payload.email, otp, minutes=5)

    # Submit email task to Celery (fire-and-forget)
    send_otp_email_task.delay(to_email=payload.email, otp=otp)
    
    return {"message": "An OTP has been sent to your email."}

@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(payload: sch.ResetPasswordSchema, db: AsyncSession = Depends(db.getDb), _: None = Depends(reset_password_limiter)):
    # Verify OTP
    if not await otp_service.checkOtp(db, payload.email, payload.otp):
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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Password was updated concurrently")
        return user

    await run_with_transient_retry(lambda: _reset_password(), db=db)

    return {"message": "Password has been reset successfully."}


@router.post("/email/verify", status_code=status.HTTP_200_OK)
async def verify_email(payload: sch.VerifyEmailRequest, db: AsyncSession = Depends(db.getDb)):
    async def _verify_email():
        user = await lock_user_row(db, email=payload.email)
        if user.email_verified:
            await db.rollback()
            return {"message": "Email already verified"}

        ok = await otp_service.checkOtp(db, payload.email, payload.otp)
        if not ok:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

        user.email_verified = True
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email verification was updated concurrently")
        return {"message": "Email verified successfully"}

    return await run_with_transient_retry(lambda: _verify_email(), db=db)


@router.post("/email/resend-otp", status_code=status.HTTP_200_OK)
async def resend_verification_otp(payload: sch.ResendVerificationOtpRequest, db: AsyncSession = Depends(db.getDb), _: None = Depends(forgot_password_limiter)):
    result = await db.execute(select(models.User).where(models.User.email == payload.email))
    user = result.scalars().first()
    if not user:
        return {"message": "If an account with this email exists, an OTP has been sent."}

    if user.email_verified:
        return {"message": "Email already verified"}

    otp = otp_service.generateOtp()
    await otp_service.saveOtp(db, payload.email, otp, minutes=5)
    
    send_verification_email_task.delay(to_email=payload.email, otp=otp)
    
    return {"message": "Verification OTP sent to your email."}



