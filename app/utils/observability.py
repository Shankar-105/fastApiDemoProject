import time
import uuid
from urllib.parse import urlparse

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.config import settings
from fastapi import FastAPI
from opentelemetry import trace
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


def _build_otlp_span_exporter():
    """Build and return an OTLP span exporter based on configured protocol and endpoint.

    Supports both HTTP/protobuf and gRPC transports. Returns None when
    no endpoint is configured (graceful no-op). Normalizes endpoint URLs
    and appends /v1/traces for HTTP. Used by configure_observability().
    """
    protocol = (
        settings.otel_exporter_otlp_protocol
        or "grpc"
    ).lower()

    endpoint = (
         settings.otel_exporter_otlp_endpoint
    )

    if not endpoint:
        logger.info("otlp_traces_export_disabled", reason="no_endpoint_configured")
        return None

    if protocol in {"http", "http/protobuf", "http-protobuf", "protobuf"}:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        base_url = f"{parsed.scheme}://{parsed.netloc or parsed.path}".rstrip("/")
        trace_endpoint = (
            base_url if base_url.endswith("/v1/traces") else f"{base_url}/v1/traces"
        )
        logger.info("configuring_otlp_tracing_http", endpoint=trace_endpoint)
        return OTLPSpanExporter(endpoint=trace_endpoint, timeout=10)

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    normalized_endpoint = endpoint
    if "://" in normalized_endpoint:
        parsed = urlparse(normalized_endpoint)
        normalized_endpoint = parsed.netloc or parsed.path.lstrip("/")

    logger.info("configuring_otlp_tracing_grpc", endpoint=normalized_endpoint)
    return OTLPSpanExporter(
        endpoint=normalized_endpoint,
        insecure=True,
        timeout=10,
    )

class LoggingASGIMiddleware:
    """ASGI middleware that provides structured request logging via structlog.

    Injects request_id and trace_id into every request/response, binds
    method/path/status_code to structlog context, and logs a 'request_processed'
    event with duration_ms on completion. Cleans up contextvars after each
    request to prevent async task leakage.

    X-Request-Id is read from the incoming header or generated as a UUID.
    X-Trace-Id is set on the response for client-side correlation.
    """

    def __init__(self, app: FastAPI):
        """Wrap the ASGI app with structured logging middleware."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Process an ASGI request: log it with timing, inject trace headers.

        Non-HTTP scopes (websockets, lifespan) pass through unmodified.
        HTTP requests get request_id binding, response header injection,
        duration measurement, and context cleanup in the finally block.
        """
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
                trace_id = "0" * 32
                if not settings.production_mode:
                    span = trace.get_current_span()
                    span_ctx = span.get_span_context() if span else None
                    if span_ctx and span_ctx.trace_id:
                        trace_id = format(span_ctx.trace_id, "032x")
                
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
    """Configure OpenTelemetry tracing, Prometheus metrics, and structured logging.

    In production mode (1 GB RAM constraint) only the LoggingASGIMiddleware
    is attached — tracing and Prometheus are skipped to conserve memory.
    Otherwise, sets up OTLP + console span processors, instruments FastAPI
    and SQLAlchemy, exposes /metrics, and adds the logging middleware.
    Called once during app factory initialization.
    """
    if settings.production_mode:
        logger.info("observability_disabled_in_production", reason="resource_constraints_1gb_ram")
        app.add_middleware(LoggingASGIMiddleware)
        return

    resource = Resource.create({SERVICE_NAME: "social-media-api"})

    provider = TracerProvider(resource=resource)
    otlp_exporter = _build_otlp_span_exporter()

    if otlp_exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    if settings.otel_console_exporter_enabled:
       provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
    Instrumentator().instrument(app).expose(app, include_in_schema=False)
    app.add_middleware(LoggingASGIMiddleware)
