from uvicorn.workers import UvicornWorker
from app.config import settings

class TunedUvicornWorker(UvicornWorker):
    """
    Gunicorn worker with config-driven Uvicorn protocol/event loop tuning.
    All settings are loaded from app.config.Settings (sourced from .env file).
    """

    CONFIG_KWARGS = {
        "loop": settings.uvicorn_loop.strip().lower(),
        "http": settings.uvicorn_http.strip().lower(),
        "timeout_keep_alive": settings.uvicorn_timeout_keep_alive,
        "lifespan": "on",
    }
