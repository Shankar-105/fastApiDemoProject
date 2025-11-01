# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import models
from app.db import engine
from app.routes import changepassword, posts,users,auth,like,connect,comment,search,me
from fastapi.middleware.cors import CORSMiddleware
models.Base.metadata.create_all(bind=engine)

# fastapi instance
app = FastAPI()
app.mount("/profilepics",StaticFiles(directory="profilepics"),name="profilepics")
# when the domain or the port changes
# browser blocks the api-url(cross origin requests COR's)
# so we need to do specify to allow all origins for now in dev scenario
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(posts.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(like.router)
app.include_router(connect.router)
app.include_router(comment.router)
app.include_router(search.router)
app.include_router(me.router)
app.include_router(changepassword.router)