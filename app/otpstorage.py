from datetime import datetime, timedelta  # For time stuff

otp_box = {}

def save_otp(email: str, otp: str, minutes: int = 5):
    # Save OTP with expire time
    expire_time = datetime.now() + timedelta(minutes=minutes)  # Now + 5 min
    otp_box[email] = {"otp": otp, "expire_time": expire_time}
    print(otp_box[email])

def check_otp(email:str,user_otp:str) -> bool:
    # Get from box
    print(otp_box)
    if email not in otp_box:
        print("1st return statement")
        return False  # No OTP
    data = otp_box[email]
    # Expired?
    if datetime.now() > data["expire_time"]:
        del otp_box[email]  # Remove old one
        return False
    # Match?
    if data["otp"] == user_otp:
        del otp_box[email]  # Remove after use (one-time)
        return True
    return False  # Wrong OTP