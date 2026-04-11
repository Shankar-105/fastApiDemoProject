# main.py
import asyncio
import json as _json
import logging
import sys
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import models, config
from app.services import redis_service as _redis_svc   # accessed via module so tests can patch redis_client
from app.db import async_engine, sync_engine
from app.routes import changepassword, posts,users,auth,like,connect,comment,search,me,feed,saved
from app.routes import notifications
from app.services.redis_service import check_redis_connection
from app.my_utils.socket_manager import manager
from chat_system import chat,chat_history,share,delete_msg,delete_shares,edit_msg,msg_info,msg_reaction,share_reaction,media_msg,clear_chat
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
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
                # User disconnected between publish and delivery - perfectly normal.
                # JSON decode error or key error - ignore and keep listening.
                pass
    except asyncio.CancelledError:
        # Clean unsubscribe before the task is marked as done.
        await ps.punsubscribe("notifications:*")
        raise   # re-raise so asyncio records the task as Cancelled, not Failed


# -- Lifespan: replaces the deprecated @app.on_event("startup"/"shutdown") --
# asynccontextmanager turns this one function into both startup AND shutdown.
# Everything before `yield` runs at startup; everything after runs at shutdown.
# FastAPI passes it to FastAPI(lifespan=lifespan) and calls it when uvicorn
# starts/stops - never at import time, so tests importing `app` are safe.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- startup --
    global _listener_task
    redis_ok = await check_redis_connection()
    if redis_ok:
        _listener_task = asyncio.create_task(_notification_listener())
    else:
        print("Skipping Redis notification listener (Redis unavailable)!")

    yield   # app is running between these two points

    # -- shutdown --
    if _listener_task:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass


# fastapi instance - lifespan wires up the startup/shutdown hooks above
app = FastAPI(lifespan=lifespan)


def _configure_observability_logger() -> logging.Logger:
    logger = logging.getLogger("observability")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not config.settings.observability_log_enabled:
        logger.disabled = True
        return logger

    # Avoid duplicate handlers when uvicorn reload imports the module more than once.
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "\033[96m[OBS]\033[0m %(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger

# Export traces to console so tracing can be validated immediately in dev.
trace.set_tracer_provider(
    TracerProvider(resource=Resource.create({SERVICE_NAME: "social-media-api"}))
)
if config.settings.otel_console_exporter_enabled:
    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

# Traces each incoming FastAPI request/response cycle.
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)

# Exposes Prometheus metrics at /metrics.
Instrumentator().instrument(app).expose(app, include_in_schema=False)

obs_logger = _configure_observability_logger()


@app.middleware("http")
async def add_trace_id_log(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    span = trace.get_current_span()
    span_ctx = span.get_span_context() if span else None
    trace_id = (
        format(span_ctx.trace_id, "032x") if span_ctx and span_ctx.trace_id else "0" * 32
    )

    obs_logger.info(
        "method=%s path=%s status=%s duration_ms=%.2f trace_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        trace_id,
    )
    response.headers["X-Trace-Id"] = trace_id
    return response

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

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root_home() -> str:
        return """
<!doctype html>
<html lang=\"en\">
<head>
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
        <p>This is the API server root page.</p>
        <p>Use the links below to explore available routes and health status.</p>
        <div class=\"links\">
            <a href=\"/docs\">OpenAPI Docs</a>
            <a href=\"/redoc\">ReDoc</a>
            <a href=\"/health\">Health Check</a>
        </div>
        <p class=\"hint\">Tip: frontend apps should call API endpoints directly, while this page is only a friendly landing screen.</p>
    </main>
</body>
</html>
        """

@app.get("/health",status_code=200)
def hello():
    return {
        "message":"fine"
    }
