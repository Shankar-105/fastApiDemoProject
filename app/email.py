from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import settings

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