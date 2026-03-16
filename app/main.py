# main.py
import asyncio
import json as _json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import models, config
from app import redis_service as _redis_svc   # accessed via module so tests can patch redis_client
from app.db import sync_engine
from app.routes import changepassword, posts,users,auth,like,connect,comment,search,me,feed,saved
from app.routes import notifications
from app.redis_service import check_redis_connection
from app.my_utils.socket_manager import manager
from chat_system import chat,chat_history,share,delete_msg,delete_shares,edit_msg,msg_info,msg_reaction,share_reaction,media_msg,clear_chat
from fastapi.middleware.cors import CORSMiddleware
# creates tables from models.py if the tables doesnt exist

models.Base.metadata.create_all(bind=sync_engine)

_listener_task: asyncio.Task | None = None

async def _notification_listener() -> None:
    ps = _redis_svc.redis_client.pubsub()
    await ps.psubscribe("notifications:*")
    try:
        async for message in ps.listen():
            if message["type"] != "pmessage":
                # Redis sends a confirmation message when you subscribe;
                # ignore everything that isn't an actual published message.
                continue
            channel: str = message["channel"]   # e.g. "notifications:42"
            try:
                user_id = int(channel.split(":")[1])
                payload = _json.loads(message["data"])
                await manager.send_personal_message(payload,user_id)
            except Exception:
                # User disconnected between publish and delivery — perfectly normal.
                # JSON decode error or key error — ignore and keep listening.
                pass
    except asyncio.CancelledError:
        # Clean unsubscribe before the task is marked as done.
        await ps.punsubscribe("notifications:*")
        raise   # re-raise so asyncio records the task as Cancelled, not Failed


# ── Lifespan: replaces the deprecated @app.on_event("startup"/"shutdown") ────
# asynccontextmanager turns this one function into both startup AND shutdown.
# Everything before `yield` runs at startup; everything after runs at shutdown.
# FastAPI passes it to FastAPI(lifespan=lifespan) and calls it when uvicorn
# starts/stops — never at import time, so tests importing `app` are safe.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    global _listener_task
    redis_ok = await check_redis_connection()
    if redis_ok:
        _listener_task = asyncio.create_task(_notification_listener())
    else:
        print("Skipping Redis notification listener (Redis unavailable)!")

    yield   # app is running between these two points

    # ── shutdown ──
    if _listener_task:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass


# fastapi instance — lifespan wires up the startup/shutdown hooks above
app = FastAPI(lifespan=lifespan)

# tells the uvicorn to render any images at the new paths while displaying profile pics or etc
# example : without this mount method suppose you hit the see your profile pic endpoint
# the postman or anyother application returns the url of the profile pic as json
# as of according ot this commit <96bd0a3> so when you run that url on broswer
# for example the url is http://127.0.0.1:8000/profilepics/yash_m77bbOnjacket.png
# without mount the uvicorn server running at http://127.0.0.1:8000 
# wouldn"t be able to render that image and give a 404 error
app.mount("/profilepics",StaticFiles(directory="profilepics"),name="profilepics")
app.mount(f"/{config.settings.media_folder}",StaticFiles(directory=f"{config.settings.media_folder}"),name=f"{config.settings.media_folder}")
app.mount("/chat-media",StaticFiles(directory="chat-media"),name="chat-media")

# when the domain or the port changes
# browser blocks the api-url(cross origin requests COR's)
# so we need to do specify to allow all origins for now in dev scenario
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://fastapi-social-vm.centralindia.cloudapp.azure.com",
    ],
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
app.include_router(feed.router)
app.include_router(saved.router)
app.include_router(notifications.router)
app.include_router(chat.router)
app.include_router(chat_history.router)
app.include_router(share.router)
app.include_router(delete_msg.router)
app.include_router(delete_shares.router)
app.include_router(edit_msg.router)
app.include_router(msg_info.router)
app.include_router(msg_reaction.router)
app.include_router(share_reaction.router)
app.include_router(media_msg.router)
app.include_router(clear_chat.router)

@app.get("/health",status_code=200)
def hello():
    return {
        "message":"fine"
    }