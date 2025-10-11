from jose import JWTError,jwt
from datetime import datetime,timedelta
import app.schemas as sch
from fastapi import status,HTTPException,Depends
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme=OAuth2PasswordBearer(tokenUrl='login')
# basically for the generation of an JWT token it requries
# 1. an ALGORITHM
# 2. some user data like suppose here user id,username
# and to this we add a newField called the expiry time
# for that amount of time the jwt token will be valid
# 3. a secret key
ALGORITHM="HS256"
SECRET_KEY="iota"
EXPIRE_TIME=3

def createAccessToken(data:dict):
    # create a copy of the data becuase
    # we create update or add a new field to it 
    # so the original one doesnt change
    dataCopy=data.copy()
    # create some expiry time 30 mins from now the token creation
    expireTime=datetime.now()+timedelta(minutes=EXPIRE_TIME)
    # update the data with expiry time convert it to seconds
    # using timestamp() mtd so that serialization to json is possible
    dataCopy.update({"expTime":int(expireTime.timestamp())})
    # encode or create a jwt token
    jwtToken=jwt.encode(dataCopy,SECRET_KEY,algorithm=ALGORITHM)
    # return the token
    return jwtToken

def verifyAccesstoken(token: str, credentials_exception):
    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id: int=payload.get("userId")
        username: str=payload.get("userName")
        if id is None or username is None:
            raise credentials_exception
        return sch.TokenModel(id=id,username=username,accessToken=token,tokenType="bearer")
    except JWTError:
        raise credentials_exception

# Get current user (for protected routes)
def getCurrentUser(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verifyAccesstoken(token,credentials_exception)