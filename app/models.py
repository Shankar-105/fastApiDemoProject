from app.db import Base
from sqlalchemy import Column,Integer,String,Boolean,ForeignKey
from sqlalchemy.sql.expression import null,text
from sqlalchemy.sql.sqltypes import TIMESTAMP

# structure or model of the db posts
# like what does a post need to have

class Post(Base):
    __tablename__='posts'
    id=Column(Integer,primary_key=True,nullable=False)
    title=Column(String,nullable=False)
    content=Column(String,nullable=False)
    enable_comments=Column(Boolean,server_default="TRUE",nullable=False)
    created_at=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),nullable=False)
    likes=Column(Integer,server_default="0",nullable=False)
    dis_likes=Column(Integer,server_default="0",nullable=False)
class User(Base):
      __tablename__='users'
      id=Column(Integer,primary_key=True,nullable=False)
      username=Column(String,nullable=False,unique=True)
      hashed_password=Column(String,nullable=False)
      email=Column(String,nullable=False)
      bio=Column(String,nullable=True)
      profile_picture=Column(String,nullable=True)
      created_at=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))

class Votes(Base):
    __tablename__='votes'
    post_id=Column(Integer,ForeignKey("posts.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    action=Column(Boolean,nullable=False)