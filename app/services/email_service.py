from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import structlog
from app.config import settings


logger = structlog.get_logger(__name__)

# setting up Gmail connection using the fastappi's
# built-in Connection system
conf = ConnectionConfig(
    MAIL_USERNAME = settings.email_username,
    MAIL_PASSWORD = settings.email_password,
    MAIL_FROM = settings.email_from,
    MAIL_PORT = settings.email_port,
    MAIL_SERVER = settings.email_server,
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False
)

# method to send OTP
async def send_otp_email(to_email:str,otp:str):
    logger.info("otp_email_sending", to_email=to_email)
    # a body for the email that will be sent
    # when this variable "html" passed as an arg to
    # the MessageSchema constructor it will be converted to
    # a html body
    html = f"""
    <h3>Password Reset OTP</h3>
    <p>Your OTP is: <b style="font-size: 20px;">{otp}</b></p>
    <p>Valid for 5 minutes only.</p>
    """
    # create an object of the built in MessageSchema class and send pass
    # all required fields to it
    message = MessageSchema(
        subject="Your OTP Code",
        recipients=[to_email],
        body=html,
        subtype="html"
    )
    fm = FastMail(conf)
    # send the email
    await fm.send_message(message)
    logger.info("otp_email_sent", to_email=to_email)


async def send_verification_email(to_email: str, otp: str):
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