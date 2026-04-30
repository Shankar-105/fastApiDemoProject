import asyncio
from app.celery_app import celery_app
from app.services.email_service import send_otp_email as _send_otp_email
from app.services.email_service import send_verification_email as _send_verification_email


@celery_app.task(bind=True, max_retries=3)
def send_otp_email(self, to_email: str, otp: str):
    try:
        asyncio.run(_send_otp_email(to_email, otp))
    except Exception as exc:
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, max_retries=3)
def send_verification_email(self, to_email: str, otp: str):
    try:
        asyncio.run(_send_verification_email(to_email, otp))
    except Exception as exc:
        countdown = 60 * (2 ** self.request.retries)
        self.retry(exc=exc, countdown=countdown)
