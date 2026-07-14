# main.py
import asyncio
import json as _json
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app import models, config
from app.services import redis_service as _redis_svc
from app.db import async_engine, sync_engine
from app.api.v1.api_router import api_v1_router
from app.services.redis_service import check_redis_connection
from app.utils.socket_manager import manager
from fastapi.middleware.cors import CORSMiddleware
from app.utils.logging import setup_logging
from app.utils.observability import configure_observability

# Initialize logging as early as possible
setup_logging()
logger = structlog.get_logger(__name__)

# -- Background Listeners --
_chat_listener_task: asyncio.Task | None = None
_notification_listener_task: asyncio.Task | None = None

async def _redis_message_listener(channel: str) -> None:
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

# -- Lifespan --
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _chat_listener_task, _notification_listener_task
    redis_ok = await check_redis_connection()
    if redis_ok:
        _chat_listener_task = asyncio.create_task(_chat_messages_listener())
        _notification_listener_task = asyncio.create_task(_notification_messages_listener())
    else:
        logger.warning("redis_listeners_skipped", detail="Redis unavailable")

    yield

    if _chat_listener_task:
        _chat_listener_task.cancel()
    if _notification_listener_task:
        _notification_listener_task.cancel()

from app.utils.exception_handlers import register_exception_handlers

# -- App Instance --
app = FastAPI(
    title="Social Media API",
    description="Scalable FastAPI backend.",
    version="1.0.0",
    lifespan=lifespan
)

configure_observability(app, async_engine)

# -- Exception Handlers --
register_exception_handlers(app)

# -- Static Files & Middleware --
app.mount("/profilepics", StaticFiles(directory="profilepics"), name="profilepics")
app.mount("/posts_media", StaticFiles(directory="posts_media"), name="posts_media")
app.mount("/chat-media", StaticFiles(directory="chat-media"), name="chat-media")
app.mount("/favicon", StaticFiles(directory="favicon"), name="favicon")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Versioned Routing (Centralized) --
app.include_router(api_v1_router, prefix="/v1")

# -- Root & Health --
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root_home() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
    <link rel="icon" type="image/png" href="/favicon/faviconIco.png" />
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
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
    <main class="card">
        <h1>FastAPI Social Backend Is Running</h1>
        <p>This is the root page of the API server.</p>
        <p>Use the links below to explore available routes and health status.</p>
        <div class="links">
            <a href="/docs">OpenAPI Docs</a>
            <a href="/redoc">ReDoc</a>
            <a href="/health">Health Check</a>
        </div>
        <p class="hint"><b>This Page is only a friendly landing screen so that it doesn't show up a 404 whenever any user is hitting the (root /) endpoint!</b></p>
    </main>
</body>
</html>
    """

@app.get("/health", status_code=200)
async def health_check():
    """
    Comprehensive health check for the API and its dependencies.
    """
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "dependencies": {
            "database": "unknown",
            "redis": "unknown",
            "rabbitmq": "unknown"
        }
    }
    
    # 1. Check Database Connection
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["dependencies"]["database"] = "connected"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["dependencies"]["database"] = f"error: {str(e)}"

    # 2. Check Redis Connection
    try:
        if await _redis_svc.redis_client.ping():
            health_status["dependencies"]["redis"] = "connected"
        else:
            health_status["status"] = "unhealthy"
            health_status["dependencies"]["redis"] = "failed ping"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["dependencies"]["redis"] = f"error: {str(e)}"

    # 3. Check RabbitMQ (via Celery Broker connection)
    try:
        from app.celery_app import celery_app
        # This checks if we can connect to the broker defined in celery_app
        with celery_app.connection_for_read() as conn:
            conn.ensure_connection(max_retries=1)
        health_status["dependencies"]["rabbitmq"] = "connected"
    except Exception as e:
        # We don't mark the whole app unhealthy if only RabbitMQ is down, 
        # as the web API can still serve requests, but background tasks will fail.
        health_status["dependencies"]["rabbitmq"] = f"error: {str(e)}"

    if health_status["status"] != "healthy":
        return JSONResponse(content=health_status, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        
    return health_status