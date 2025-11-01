from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import settings

# Setup Gmail connection
conf = ConnectionConfig(
    MAIL_USERNAME = settings.email_username,
    MAIL_PASSWORD = settings.email_password,
    MAIL_FROM = settings.email_from,
    MAIL_PORT = settings.email_port,
    MAIL_SERVER = settings.email_server,
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False
)

# Function to send OTP
async def send_otp_email(to_email:str,otp:str):
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