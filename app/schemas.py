from pydantic import BaseModel,ConfigDict,Field
from datetime import datetime
from app.models import Post
from typing import Optional
from fastapi import Query
# while the user is creating a post user shouldn't send any unncessary
# data other than the below mentioned fields when user does this
# we need to warn user that correct data isn't sent for creating a post
# so we define a schema to tell the frontend what need to be sent by the 
# user while creating a post 
# structure or schema of the post using pydantic's BaseModel class
class PostEssentials(BaseModel):
    title:str
    content:str
    enable_comments:bool=True
    hashtags:str=None

# while the user retrives the posts or when a new post is created
# there's no need of showing the user all the data about the post
# rather only data to be seen is shown so the below schema is a 
# pydantic model while returning post data to user
class PostResponse(BaseModel):
    id:int
    title:str
    created_at:datetime
    user_id:int
    model_config = ConfigDict(
        from_attributes=True
    )

# user shouldn't send any unncessary data so we need
# to validate it through a model like below
# if user sends any other data while signUp other than
# those 'username and 'passsword' then through this schema
# pydantic sends an warning to the frontend to tell the user that 
# correct data isn't sent via our api's
class UserEssentials(BaseModel):
    username:str
    password: str = Field(..., max_length=72)
    nickname:str

# when the new account for a user is created there's no meaning in
# showing all his data so we just show him what's to be shown after 
# the creation of an account
class UserResponse(BaseModel):
    id:int
    username:str
    created_at:datetime
    model_config = ConfigDict( 
        from_attributes=True
    )

# class UserLoginCred(UserEssentials):
#     pass

class TokenModel(BaseModel):
    id:int
    username:str
    accessToken:str
    tokenType:str

class VoteModel(BaseModel):
    post_id:int
    choice:bool
class VoteResponseModel(BaseModel):
    message:str

class UserUpdateInfo(BaseModel):
  username:Optional[str]=None
  bio:Optional[str]=None

class Comment(BaseModel):
    post_id:int
    content:str

class PostAnalytics(BaseModel):
    post_id:int
    views:int
    likes:int
    dislikes:int
    comments:int
    createdOn:datetime

class EditCommentModel(BaseModel):
    comment_content:str

class CommentVoteModel(BaseModel):
    comment_id:int
    choice:bool
class SearchFeature(BaseModel):
    q:str=Query(None, description="Search query")
    limit:int=10
    offset:int=0
    orderBy:Optional[str]="created_at"