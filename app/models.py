from .db import Base
from sqlalchemy import Column,Integer,String,Boolean
from sqlalchemy.sql.expression import null

class Post(Base):
    __tablename__='posts'
    id=Column(Integer,primary_key=True,nullable=False)
    title=Column(String,nullable=False)
    content=Column(String,nullable=False)
    enableComments=Column(Boolean,nullable=False)