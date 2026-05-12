# main.py
import asyncio
import json as _json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app import models, config
from app.services import redis_service as _redis_svc   # accessed via module so tests can patch redis_client
from app.db import async_engine, sync_engine
from app.routes import changepassword, posts,users,auth,like,connect,comment,search,me,feed,saved
from app.routes import notifications
from app.routes import celery_tasks
from app.services.redis_service import check_redis_connection
from app.utils.socket_manager import manager
from chat_system import chat,chat_history,share,delete_msg,delete_shares,edit_msg,msg_info,msg_reaction,share_reaction,media_msg,clear_chat
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from app.utils.observability import configure_observability


# install the pg_trgm extension before creating the tables
with sync_engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

# creates all the tables from models.py from scratch

models.Base.metadata.create_all(bind=sync_engine)

_chat_listener_task: asyncio.Task | None = None
_notification_listener_task: asyncio.Task | None = None


async def _redis_message_listener(channel: str) -> None:
    """Deliver Redis pub/sub messages to locally connected websocket users."""
    ps = _redis_svc.redis_client.pubsub()
    await ps.subscribe(channel)
    try:
        async for message in ps.listen():
            if message["type"] != "message":
                continue
            try:
                payload = _json.loads(message["data"])
                receiver_id = payload.get("receiver_id")
                if receiver_id is not None:
                    await manager.send_personal_message(payload, receiver_id)
            except Exception:
                pass
    except asyncio.CancelledError:
        await ps.unsubscribe(channel)
        raise


async def _chat_messages_listener() -> None:
    return await _redis_message_listener("chat:messages")


async def _notification_messages_listener() -> None:
    return await _redis_message_listener("notifications:messages")

# -- Lifespan: replaces the deprecated @app.on_event("startup"/"shutdown") --
# asynccontextmanager turns this one function into both startup AND shutdown.
# Everything before `yield` runs at startup; everything after runs at shutdown.
# FastAPI passes it to FastAPI(lifespan=lifespan) and calls it when uvicorn
# starts/stops - never at import time, so tests importing `app` are safe.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- startup --
    global _chat_listener_task, _notification_listener_task
    redis_ok = await check_redis_connection()
    if redis_ok:
        _chat_listener_task = asyncio.create_task(_chat_messages_listener())
        _notification_listener_task = asyncio.create_task(_notification_messages_listener())
        # Redis listeners started. Post-view flushing is handled by Celery beat.
    else:
        print("Skipping Redis listeners (Redis unavailable)!")

    yield   # app is running between these two points

    # -- shutdown --
    if _chat_listener_task:
        _chat_listener_task.cancel()
        try:
            await _chat_listener_task
        except asyncio.CancelledError:
            pass
    if _notification_listener_task:
        _notification_listener_task.cancel()
        try:
            await _notification_listener_task
        except asyncio.CancelledError:
            pass
    # post view flushing is handled by Celery beat; nothing to shut down here.

# fastapi instance - lifespan wires up the startup/shutdown hooks above
app = FastAPI(lifespan=lifespan)
if config.settings.benchmark_mode_enabled:
    pass
else:
    configure_observability(app, async_engine)

# tells the uvicorn to render any images at the new paths while displaying profile pics or etc
# example : without this mount method suppose you hit the see your profile pic endpoint
# the postman or anyother application returns the url of the profile pic as json
# as of according ot this commit <96bd0a3> so when you run that url on broswer
# for example the url is http://127.0.0.1:8000/profilepics/yash_m77bbOnjacket.png
# without mount the uvicorn server running at http://127.0.0.1:8000 
# wouldn"t be able to render that image and give a 404 error
app.mount("/profilepics",StaticFiles(directory="profilepics"),name="profilepics")
app.mount("/posts_media", StaticFiles(directory="posts_media"), name="posts_media")
app.mount("/chat-media",StaticFiles(directory="chat-media"),name="chat-media")
app.mount("/favicon", StaticFiles(directory="favicon"), name="favicon")
# Favicon: prefer file at /favicon/favicon.png,

# when the domain or the port changes
# browser blocks the api-url(cross origin requests COR's)
# so we need to do specify to allow all origins for now in dev scenario
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(posts.router)
app.include_router(me.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(like.router)
app.include_router(connect.router)
app.include_router(comment.router)
app.include_router(search.router)
app.include_router(changepassword.router)
app.include_router(feed.router)
app.include_router(saved.router)
app.include_router(notifications.router)
app.include_router(chat.router)
app.include_router(celery_tasks.router)
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

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root_home() -> str:
        return """
<!doctype html>
<html lang=\"en\">
<head>
    <link rel="icon" type="image/png" href="/favicon/faviconIco.png" />
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>FastAPI Social Backend</title>
    <style>
        :root {
            --bg1: #f7fbff;
            --bg2: #e8f1ff;
            --ink: #10243e;
            --muted: #3e5b7f;
            --accent: #1f6feb;
            --card: #ffffff;
            --border: #d7e3f4;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: Segoe UI, Tahoma, Geneva, Verdana, sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 10%, #ffffff 0%, transparent 35%),
                radial-gradient(circle at 90% 80%, #dbeafe 0%, transparent 30%),
                linear-gradient(135deg, var(--bg1), var(--bg2));
            display: grid;
            place-items: center;
            padding: 24px;
        }
        .card {
            width: min(680px, 100%);
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 30px;
            box-shadow: 0 12px 40px rgba(16, 36, 62, 0.09);
        }
        h1 {
            margin: 0 0 10px;
            font-size: clamp(1.55rem, 2.2vw, 2.05rem);
            letter-spacing: 0.2px;
        }
        p {
            margin: 8px 0;
            color: var(--muted);
            line-height: 1.6;
        }
        .links {
            margin-top: 18px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        a {
            text-decoration: none;
            color: var(--accent);
            background: #eef5ff;
            border: 1px solid #cfe2ff;
            padding: 9px 13px;
            border-radius: 10px;
            font-weight: 600;
            transition: transform 0.12s ease, background 0.12s ease;
        }
        a:hover {
            background: #e4efff;
            transform: translateY(-1px);
        }
        .hint {
            margin-top: 14px;
            font-size: 0.94rem;
        }
    </style>
</head>
<body>
    <main class=\"card\">
        <h1>FastAPI Social Backend Is Running</h1>
        <p>This is the root page of the API server.</p>
        <p>Use the links below to explore available routes and health status.</p>
        <div class=\"links\">
            <a href=\"/docs\">OpenAPI Docs</a>
            <a href=\"/redoc\">ReDoc</a>
            <a href=\"/health\">Health Check</a>
        </div>
        <p class=\"hint\"><b>This Page is only a friendly landing screen so that it doesn't show up a 404 whenever any user is hitting the (root /) endpoint!</b></p>
    </main>
</body>
</html>
        """

@app.get("/health",status_code=200)
def hello():
    return {
        "message":"fine"
    }
