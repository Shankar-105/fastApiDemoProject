from app.db import Base
from sqlalchemy import Column,Integer,String,Boolean
from sqlalchemy.sql.expression import null,text
from sqlalchemy.sql.sqltypes import TIMESTAMP

# structure or model of the db posts
# like what does a post need to have

class Post(Base):
    __tablename__='posts'
    id=Column(Integer,primary_key=True,nullable=False)
    title=Column(String,nullable=False)
    content=Column(String,nullable=False)
    enableComments=Column(Boolean,server_default="TRUE",nullable=False)
    createdAt=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))

class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True,nullable=False)
    username=Column(String,nullable=False,unique=True)
    email=Column(String,nullable=False,unique=True)
    password=Column(String,nullable=False)
    createdAt=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))