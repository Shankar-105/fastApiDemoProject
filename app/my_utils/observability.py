import logging
import sys
import time
from app.config import settings
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator


def _configure_observability_logger() -> logging.Logger:
    logger = logging.getLogger("observability")
    logger.setLevel(logging.INFO)
    logger.propagate = False

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


class LoggingASGIMiddleware:
    """Lightweight ASGI middleware that logs request timing and injects X-Trace-Id."""

    def __init__(self, app: FastAPI):
        self.app = app
        self.logger = _configure_observability_logger()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        from starlette.datastructures import MutableHeaders
        from starlette.requests import Request

        req = Request(scope, receive=receive)
        start = time.perf_counter()
        status_code = None
        trace_id = "0" * 32

        async def send_wrapper(message):
            nonlocal status_code, trace_id
            if message["type"] == "http.response.start":
                status_code = message.get("status")
                headers = MutableHeaders(scope=message)
                span = trace.get_current_span()
                span_ctx = span.get_span_context() if span else None
                trace_id = (
                    format(span_ctx.trace_id, "032x") if span_ctx and span_ctx.trace_id else "0" * 32
                )
                headers.append("X-Trace-Id", trace_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.perf_counter() - start) * 1000
        self.logger.info(
            "method=%s path=%s status=%s duration_ms=%.2f trace_id=%s",
            req.method,
            req.url.path,
            status_code or "-",
            duration_ms,
            trace_id,
        )


def configure_observability(app: FastAPI, async_engine) -> None:
    trace.set_tracer_provider(
        TracerProvider(resource=Resource.create({SERVICE_NAME: "social-media-api"}))
    )
    if settings.otel_console_exporter_enabled:
       trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
    Instrumentator().instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(LoggingASGIMiddleware)