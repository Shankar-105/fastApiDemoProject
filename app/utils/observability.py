import os
import time
import uuid
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.config import settings
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator

from app.utils.logging import setup_logging

# Initialize logging as soon as this module is imported
setup_logging()
logger = structlog.get_logger(__name__)

class LoggingASGIMiddleware:
    """
    Improved ASGI middleware using structlog for structured request logging.
    Injects request_id, trace_id into context and logs request results.
    """

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
        
        # Clear any leaked context from previous tasks and start fresh
        clear_contextvars()
        
        # Generate or extract request ID
        request_id = req.headers.get("X-Request-Id", str(uuid.uuid4()))
        
        # Bind initial request context
        bind_contextvars(
            request_id=request_id,
            method=req.method,
            path=req.url.path,
        )

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status")
                headers = MutableHeaders(scope=message)
                
                # Get current trace ID from OpenTelemetry
                span = trace.get_current_span()
                span_ctx = span.get_span_context() if span else None
                trace_id = (
                    format(span_ctx.trace_id, "032x") if span_ctx and span_ctx.trace_id else "0" * 32
                )
                
                # Add headers to response for client-side tracing
                headers.append("X-Trace-Id", trace_id)
                headers.append("X-Request-Id", request_id)
                
                # Bind status code to context for the final log
                bind_contextvars(status_code=status_code)
                
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            # Log the request completion with timing
            logger.info(
                "request_processed",
                duration_ms=round(duration_ms, 2),
            )
            # Clear context variables to avoid leakage in async tasks
            clear_contextvars()

def configure_observability(app: FastAPI, async_engine) -> None:
    resource = Resource.create({SERVICE_NAME: "social-media-api"})
    trace.set_tracer_provider(TracerProvider(resource=resource))
    
    is_docker = settings.database_host == "db"
    
    alloy_endpoint = "http://alloy:4318/v1/traces" if is_docker else "http://127.0.0.1:4318/v1/traces"
    
    logger.info("configuring_otlp_tracing_http", endpoint=alloy_endpoint)
    
    otlp_exporter = OTLPSpanExporter(
        endpoint=alloy_endpoint,
        timeout=10
    )
    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

    if settings.otel_console_exporter_enabled:
       trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
    Instrumentator().instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(LoggingASGIMiddleware)
