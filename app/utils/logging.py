import logging
import sys
from typing import Any, Dict, List
import structlog
from structlog.types import Processor
from opentelemetry import trace
from app.config import settings

def add_otel_trace_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds OpenTelemetry trace and span IDs to the log event.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span_context = span.get_span_context()
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict

def drop_color_if_prod(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure no color codes in production JSON logs.
    """
    if settings.production_mode:
        event_dict.pop("_record", None)
        event_dict.pop("_from_structlog", None)
    return event_dict

from celery.signals import after_setup_logger, after_setup_task_logger

def setup_logging():
    """
    Configures structlog for the entire application.
    Supports development (pretty console) and production (structured JSON).
    """
    
    # Common processors for both modes
    shared_processors: List[Processor] = [
        # Merges context variables set via structlog.contextvars.bind_contextvars()
        structlog.contextvars.merge_contextvars,
        # Adds log level (info, debug, etc.)
        structlog.processors.add_log_level,
        # Adds timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Adds OpenTelemetry trace info
        add_otel_trace_id,
        # If an exception is passed, it renders it nicely
        structlog.processors.format_exc_info,
        # Adds information about where the log was called
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    if settings.production_mode:
        # Production Mode: Optimized for log aggregators (Loki/ELK)
        # - Single-line JSON
        # - No colors
        # - INFO level default
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
        log_level = logging.INFO
    else:
        # Development Mode: Optimized for humans
        # - Pretty colors
        # - Multiline tracebacks
        # - DEBUG level default
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        log_level = logging.DEBUG

    if settings.benchmark_mode_enabled:
        log_level = logging.ERROR

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    # Pipe standard library logging (uvicorn, etc.) into structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Reduce noise from 3rd party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiosmtplib").setLevel(logging.WARNING)

@after_setup_logger.connect
@after_setup_task_logger.connect
def setup_celery_logging(logger, **kwargs):
    """
    Ensure Celery workers use structlog.
    """
    setup_logging()

# Export a default logger for quick use, though get_logger(__name__) is preferred
logger = structlog.get_logger("app")