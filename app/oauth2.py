from jose import JWTError,jwt
from datetime import datetime,timedelta
import app.schemas as sch
from fastapi import status,HTTPException,Depends
from fastapi.security import OAuth2PasswordBearer
from app.config import settings as cg
# a scheme for Extracting the sent JWT token 
# from the Authorization Header
oauth2_scheme=OAuth2PasswordBearer(tokenUrl='login')

# basically for the generation of an JWT token it requries
# 1. an ALGORITHM
# 2. some user data like suppose here user id,username
# and to this we add a newField called the expiry time
# for that amount of time the jwt token will be valid
# 3. a secret key
ALGORITHM=cg.algorithm
SECRET_KEY=cg.secret_key
EXPIRE_TIME=cg.access_token_expire_time

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
        # decode's the token which returns a dict of the sent user info 
        # while creating a token (userId,userName) 
        decodedToken=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # extract those userId and userName from the returned dict
        id: int=decodedToken.get("userId")
        username: str=decodedToken.get("userName")
        # if they aren't found meaning a malformed jwt token is sent
        # so we raise an exception
        if id is None or username is None:
            raise credentials_exception
        # if not then we create a TokenModel and return it to the protected routes
        return sch.TokenModel(id=id,username=username,accessToken=token,tokenType="bearer")
    # if the token itself is invalid we raise a JWTError
    except JWTError:
        raise credentials_exception

# Get current user (for protected routes)
# in the parentheses the Depends(oauth2_scheme) returns the
# JWT Token which is stored in the token variable below
# and sent to the verifyAccesstoken() mtd
def getCurrentUser(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verifyAccesstoken(token,credentials_exception)