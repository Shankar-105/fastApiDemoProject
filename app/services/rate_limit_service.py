import math
import time

from fastapi import Depends, HTTPException, Request, status
from redis.exceptions import WatchError

from app import models, oauth2
from app.services import redis_service as _redis_svc
from app.config import settings


async def _consume_token_bucket(key: str, max_calls: int, window: int) -> tuple[bool, int]:
    now_ms = int(time.time() * 1000)
    refill_window_ms = max(window, 1) * 1000

    if max_calls <= 0:
        return False, 1

    refill_per_ms = max_calls / refill_window_ms
    ttl_ms = max(refill_window_ms * 2, 1000)

    while True:
        pipe = _redis_svc.redis_client.pipeline()
        try:
            await pipe.watch(key)
            tokens_raw, last_refill_raw = await pipe.hmget(key, "tokens", "ts")

            tokens = float(tokens_raw) if tokens_raw is not None else float(max_calls)
            last_refill_ms = int(last_refill_raw) if last_refill_raw is not None else now_ms

            elapsed_ms = max(0, now_ms - last_refill_ms)
            refill_amount = elapsed_ms * refill_per_ms
            tokens = min(float(max_calls), tokens + refill_amount)

            if tokens >= 1:
                tokens -= 1
                allowed = True
                retry_after_ms = 0
            else:
                allowed = False
                deficit = 1 - tokens
                retry_after_ms = math.ceil(deficit / refill_per_ms)

            pipe.multi()
            pipe.hset(key, mapping={"tokens": str(tokens), "ts": str(now_ms)})
            pipe.pexpire(key, ttl_ms)
            await pipe.execute()
            return allowed, max(1, math.ceil(retry_after_ms / 1000))
        except WatchError:
            continue

async def _check(key: str, max_calls: int, window: int) -> None:
    try:
        allowed, retry_after = await _consume_token_bucket(key, max_calls, window)
        if not allowed:
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
# Routes import these directly:  from app.services.rate_limit_service import login_limiter

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
