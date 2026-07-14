from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import structlog
from app.config import settings


logger = structlog.get_logger(__name__)

# We use fastapi-mail with a Gmail SMTP connection for sending OTPs and
# verification emails.  The config is loaded from .env so credentials are
# never hardcoded.
conf = ConnectionConfig(
    MAIL_USERNAME = settings.email_username,
    MAIL_PASSWORD = settings.email_password,
    MAIL_FROM = settings.email_from,
    MAIL_PORT = settings.email_port,
    MAIL_SERVER = settings.email_server,
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False
)


async def send_otp_email(to_email: str, otp: str):
    """Send a password-reset OTP to *to_email*.

    The OTP is rendered in an HTML email with a 5-minute validity notice.
    Called from POST /v1/auth/password/forgot and POST /v1/auth/password/reset.
    """
    logger.info("otp_email_sending", to_email=to_email)
    html = f"""
    <h3>Password Reset OTP</h3>
    <p>Your OTP is: <b style="font-size: 20px;">{otp}</b></p>
    <p>Valid for 5 minutes only.</p>
    """
    message = MessageSchema(
        subject="Your OTP Code",
        recipients=[to_email],
        body=html,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    logger.info("otp_email_sent", to_email=to_email)


async def send_verification_email(to_email: str, otp: str):
    """Send an email-verification OTP to *to_email*.

    Called from POST /v1/users/register immediately after account creation.
    The user must verify their email before they can log in.
    """
    logger.info("verification_email_sending", to_email=to_email)
    html = f"""
    <h3>Verify Your Email</h3>
    <p>Use this OTP to verify your account: <b style="font-size: 20px;">{otp}</b></p>
    <p>Valid for 5 minutes only.</p>
    """
    message = MessageSchema(
        subject="Verify your email",
        recipients=[to_email],
        body=html,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    logger.info("Verification email sent", extra={"extra_info": {"to_email": to_email}})
