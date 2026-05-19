import logging
import sys
from typing import Any, Dict, Optional
import json
from datetime import datetime
from opentelemetry import trace
from contextvars import ContextVar

# Context variables for binding request-specific data
user_id_ctx: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

class StructuredJSONFormatter(logging.Formatter):
    """
    JSON formatter for structured production logging.
    """
    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        span_context = span.get_span_context()
        
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
        }

        user_id = user_id_ctx.get()
        if user_id:
            log_data["user_id"] = user_id
        
        request_id = request_id_ctx.get()
        if request_id:
            log_data["request_id"] = request_id

        if span_context and span_context.is_valid:
            log_data["trace_id"] = format(span_context.trace_id, "032x")
            log_data["span_id"] = format(span_context.span_id, "016x")

        if hasattr(record, "extra_info"):
            log_data.update(record.extra_info)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

class PrettyConsoleFormatter(logging.Formatter):
    """
    Pretty console formatter for development.
    """
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    cyan = "\x1b[36;20m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" + reset,
        logging.INFO: cyan + "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" + reset,
        logging.WARNING: yellow + "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" + reset,
        logging.CRITICAL: bold_red + "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" + reset
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        
        message = formatter.format(record)
        
        context_parts = []
        user_id = user_id_ctx.get()
        if user_id:
            context_parts.append(f"user_id={user_id}")
        
        request_id = request_id_ctx.get()
        if request_id:
            context_parts.append(f"req_id={request_id}")
            
        if context_parts:
            message += f" \033[90m({', '.join(context_parts)})\033[0m"
            
        return message

def setup_production_logging():
    """
    Configures structured JSON logging for production environment.
    """
    from app.config import settings
    
    root_logger = logging.getLogger()
    
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    root_logger.setLevel(logging.INFO)
    handler.setFormatter(StructuredJSONFormatter())
    root_logger.addHandler(handler)
    
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return root_logger

def setup_development_logging():
    """
    Configures pretty console logging for development environment.
    """
    from app.config import settings
    
    root_logger = logging.getLogger()
    
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    root_logger.setLevel(logging.DEBUG)
    handler.setFormatter(PrettyConsoleFormatter())
    root_logger.addHandler(handler)
    
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return root_logger

def setup_benchmark_logging():
    """
    Disables logging completely for benchmark mode.
    """
    root_logger = logging.getLogger()
    
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(PrettyConsoleFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.ERROR)
    
    return root_logger

# Initialize logger
logger = logging.getLogger("app")