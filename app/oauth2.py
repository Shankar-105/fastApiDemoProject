from jose import JWTError,jwt
from datetime import datetime,timedelta
ALGORITHM="HS256"
SECERT_KEY="iota"
EXPIRE_TIME=30

def createAccessToken(data:dict):
    dataCopy=data.copy()
    expireTime=datetime.now()+timedelta(minutes=EXPIRE_TIME)
    dataCopy.update({"expTime":int(expireTime.timestamp())})
    jwtToken=jwt.encode(dataCopy,SECERT_KEY,algorithm=ALGORITHM)
    return jwtToken