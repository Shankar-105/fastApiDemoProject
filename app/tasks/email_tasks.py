import asyncio
from app.celery_app import celery_app
from app.services.email_service import send_otp_email as _send_otp_email
from app.services.email_service import send_verification_email as _send_verification_email


@celery_app.task(bind=True, max_retries=3)
def send_otp_email(self, to_email: str, otp: str):
    """Send an OTP email asynchronously via Celery.

    Wraps the synchronous email service's send_otp_email with asyncio.run
    so it can be dispatched from the request-response cycle without blocking.
    Retries up to 3 times with exponential backoff (60s, 120s, 240s).
    """
    try:
        asyncio.run(_send_otp_email(to_email, otp))
    except Exception as exc:
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=3)
def send_verification_email(self, to_email: str, otp: str):
    """Send a verification email asynchronously via Celery.

    Wraps the synchronous email service's send_verification_email with
    asyncio.run. Retries up to 3 times with exponential backoff.
    Used during signup email verification flow.
    """
    try:
        asyncio.run(_send_verification_email(to_email, otp))
    except Exception as exc:
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)
