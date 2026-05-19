import logging
import sys
import time
import uuid
from app.config import settings
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator
from app.utils.logging import request_id_ctx, user_id_ctx, setup_logging

# Initialize structured logging
setup_logging()
logger = logging.getLogger("app")

class LoggingASGIMiddleware:
    """Lightweight ASGI middleware that logs request timing and injects X-Trace-Id."""

    def __init__(self, app: FastAPI):
        self.app = app

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
        
        # Generate or extract request ID
        request_id = req.headers.get("X-Request-Id", str(uuid.uuid4()))
        request_id_token = request_id_ctx.set(request_id)
        
        # User ID context will be set by a separate dependency/middleware after auth
        user_id_token = user_id_ctx.set(None)

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
                headers.append("X-Request-Id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Request processed",
                extra={
                    "extra_info": {
                        "method": req.method,
                        "path": req.url.path,
                        "status": status_code or "-",
                        "duration_ms": round(duration_ms, 2),
                        "trace_id": trace_id,
                        "request_id": request_id
                    }
                }
            )
            # Reset context variables
            request_id_ctx.reset(request_id_token)
            user_id_ctx.reset(user_id_token)


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
