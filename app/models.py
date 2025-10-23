from app.db import Base
from sqlalchemy import Column,Integer,String,Boolean,ForeignKey,Table
from sqlalchemy.sql.expression import null,text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.orm import relationship
# structure or model of the db posts
# like what does a post need to have

connections = Table(
    'connections', Base.metadata,
    Column('followed_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('follower_id', Integer, ForeignKey('users.id'), primary_key=True)
)
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
      password=Column(String,nullable=False)
      nickname=Column(String,nullable=False)
      bio=Column(String,nullable=True)
      profile_picture=Column(String,nullable=True)
      created_at=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))
      followers=Column(Integer,server_default="0",nullable=False)
      following=Column(Integer,server_default="0",nullable=False)
      # added relationship between the posts table and the users table so that
      # when you actually need all the posts of a user there's no need from now on 
      # to go check the posts table and query it for Posts.user_id==currentUser.id
      # inorder to get all posts of a certain user but rather by declaring this relationship
      # you just do the currentUser.posts and sqlAlchemy internally does the joins
      # and retrievs you all of the users posts!
      posts=relationship('Post',backref='user')
      # a many to many relationship
      followers = relationship(
        'User',
        secondary=connections,  # The middle table
        primaryjoin=(connections.c.followed_id == id),  # "I am the follwed guyy"
        secondaryjoin=(connections.c.follower_id == id),  # "They are my followers"
        backref='following'  # reverse property
    )
class Votes(Base):
    __tablename__='votes'
    post_id=Column(Integer,ForeignKey("posts.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    action=Column(Boolean,nullable=False)