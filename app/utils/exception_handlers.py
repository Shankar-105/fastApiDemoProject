import structlog
from structlog.contextvars import get_contextvars
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError
from app.utils.exceptions import AppException

logger = structlog.get_logger(__name__)

def register_exception_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.error(
            "app_exception",
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
            status_code=exc.status_code
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": get_contextvars().get("request_id")
            }
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(request: Request, exc: IntegrityError):
        logger.error("database_integrity_error", error=str(exc.orig))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error_code": "INTEGRITY_ERROR",
                "message": "A database integrity error occurred.",
                "request_id": get_contextvars().get("request_id")
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning("validation_error", details=exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Input validation failed.",
                "details": exc.errors(),
                "request_id": get_contextvars().get("request_id")
            }
        )

    @app.exception_handler(Exception)
    async def universal_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": get_contextvars().get("request_id")
            }
        )
    
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("sqlalchemy_error", error=str(exc))
        # You can do smart mapping here
        return JSONResponse(
            status_code=400 if "unique" in str(exc).lower() else 500,
            content={
                "error_code": "DATABASE_ERROR",
                "message": "Database operation failed.",
                "request_id": get_contextvars().get("request_id")
            }
        )

    @app.exception_handler(OperationalError)
    async def operational_error_handler(request: Request, exc: OperationalError):
        logger.exception("database_operational_error", error=str(exc.orig))
        return JSONResponse(
            status_code=503,  # Service Unavailable for transient issues
            content={
                "error_code": "DATABASE_TEMPORARY_ERROR",
                "message": "Temporary database issue. Please retry.",
                "request_id": get_contextvars().get("request_id")
            }
        )