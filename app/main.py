# main.py
from fastapi import FastAPI,Response,status,HTTPException,Depends,Body
from typing import Optional,List
import app.schemas as sch
from app import models
from app.db import engine,getDb
from sqlalchemy.orm import Session
from app.routes.posts import router as posts_router
from app.routes.users import router as users_router
from app.routes.auth import router as auth_router

models.Base.metadata.create_all(bind=engine)

# fastapi instance
app = FastAPI()

# testing whether the db is connected or not
# testing successfull everything working fine!
'''
@app.get("/sqlAlchemyTesting")
def test(db:Session=Depends(getDb)):
    posts=db.query(models.Post).all()
    if not posts:
        return {"data":"no posts available"}
    return {"allPosts":posts}
'''
# sometimes the connection to the db may fail
# despite of passing the correct args to the params
# so we usaually try again to connect to the db
# here i have put the connection code inside a try block so that
# when the connection fails the program shouldn't crash
# and trying to connect again and again using the while loop
# until we make sure the connection is successfull
# the connection is set via sqlAlchemy so need to
# setup connnection again to psycopg
# this set up requires needs these packages to be imported:
# import psycopg2
# from psycopg2.extras import RealDictCursor
'''i=10
while i:
    try:
        conn=psycopg2.connect(host="localhost",database="fastApi",user="postgres",password="iota143",cursor_factory=RealDictCursor)
        myCursor=conn.cursor()
        print("DataBase Connection SuccessFull")
        break
    except Exception as error:
        i=i-1
        print("Connection to the Database Failed with an error : ",error,"trying again to connect")
        time.sleep(3)
'''

# basically when we don't connect to database we need
# some ds to store our posts and this list below does that
# but this is just for testing purposes becuz
# all the posts data will be lost after server stops 

# allPosts=[]


# find a post with id -> {id} while working on with list 'allPosts'
# when we don't use databases and just code up with lists
''' def findPost(id:int):

    reqPost=None
    for i in allPosts:
        if i['id'] == id:
            reqPost=i
            break
    return reqPost '''


# find the index of a post with certain id -> {id} when we dont use databases
# and jsut code up with lists
''' def findPostIndex(id:int):
    idx=-1
    for i in range(len(allPosts)):
        if allPosts[i]['id'] == id:
            idx=i
            break
    return idx '''    
app.include_router(posts_router)
app.include_router(users_router)
app.include_router(auth_router)