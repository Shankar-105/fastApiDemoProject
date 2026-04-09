from fastapi import Depends, HTTPException, Request, status
from app import models, oauth2
from app.services import redis_service as _redis_svc
from app.config import settings


async def _check(key: str, max_calls: int, window: int) -> None:
    try:
        count = await _redis_svc.redis_client.incr(key)
        if count == 1:
            # First hit in this window — start the expiry clock
            await _redis_svc.redis_client.expire(key, window)
        if count > max_calls:
            ttl = await _redis_svc.redis_client.ttl(key)
            retry_after = max(ttl, 1)   # guard against 0 if key just expired
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise
    except Exception:
        # Redis unavailable — let the request through without rate limiting
        pass


def ip_rate_limit(endpoint_id: str, max_calls: int, window: int):
    async def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"rl:{endpoint_id}:ip:{ip}"
        await _check(key, max_calls, window)

    return dependency


def user_rate_limit(endpoint_id: str, max_calls: int, window: int):
    async def dependency(current_user: models.User = Depends(oauth2.getCurrentUser)) -> None:
        key = f"rl:{endpoint_id}:user:{current_user.id}"
        await _check(key, max_calls, window)

    return dependency


# Pre-configured dependency instances
# Routes import these directly:  from app.rate_limiter import login_limiter

# ip level rate limiters
login_limiter = ip_rate_limit("login",settings.rl_login_max,settings.rl_login_window)
signup_limiter = ip_rate_limit("signup",settings.rl_signup_max,settings.rl_signup_window)
forgot_password_limiter = ip_rate_limit("forgot_password",settings.rl_forgot_password_max,settings.rl_forgot_password_window)
reset_password_limiter = ip_rate_limit("reset_password",settings.rl_reset_password_max,settings.rl_reset_password_window)
refresh_limiter = ip_rate_limit("refresh",settings.rl_refresh_max,settings.rl_refresh_window)

# user level rate limiters
change_password_limiter = user_rate_limit("change_password_otp",settings.rl_change_password_max,settings.rl_change_password_window)
reset_password_auth_limiter = user_rate_limit("reset_password_auth",settings.rl_reset_password_auth_max,settings.rl_reset_password_auth_window)
comment_limiter = user_rate_limit("comment",settings.rl_comment_max,settings.rl_comment_window)
create_post_limiter = user_rate_limit("create_post",settings.rl_create_post_max,settings.rl_create_post_window)
follow_limiter = user_rate_limit("follow",settings.rl_follow_max,settings.rl_follow_window)
