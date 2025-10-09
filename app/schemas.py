from pydantic import BaseModel,ConfigDict
from datetime import datetime
# Front end shouldn't send any uneccessary data 
# we need to define a schema that frontend need to follow when sending data from user
# structure or schema of the post using pydantic's BaseModel class

class PostEssentials(BaseModel):
    title:str
    content:str
    enableComments:bool=True

# while creating or updating post we
# obviously need to fill those essentials
# so our schema for the data while creating or updating 
# the posts will be the same
class CreatePost(PostEssentials):
    pass

class PostResponse(BaseModel):
    id:int
    title:str
    createdAt:datetime
    model_config = ConfigDict(
        from_attributes=True
    )