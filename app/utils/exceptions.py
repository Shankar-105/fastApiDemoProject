from typing import Any, Dict, Optional
from fastapi import status

class AppException(Exception):
    """Base class for all application-specific exceptions.

    Carries a user-facing message, an HTTP status code, a machine-readable
    error_code (e.g. 'RESOURCE_NOT_FOUND'), and optional structured details.
    Caught by app_exception_handler in exception_handlers.py and serialized
    to a consistent JSON error envelope.
    """
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

class ResourceNotFoundException(AppException):
    """Raised when a requested resource (user, post, comment, etc.) cannot be found.

    Constructs a descriptive message like 'User with identifier 42 not found'.
    Returns 404. Used extensively in service and route layers.
    """
    def __init__(self, resource: str, identifier: Any, details: Optional[Dict[str, Any]] = None):
        message = f"{resource} with identifier {identifier} not found"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            details=details
        )

class ValidationException(AppException):
    """Raised when business-logic validation fails beyond Pydantic schema checks.

    Returns 400. Used when, e.g., a user tries to follow themselves or
    provide an unsupported value that Pydantic cannot catch statically.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR",
            details=details
        )

class AuthenticationException(AppException):
    """Raised when a user cannot be authenticated (invalid/missing token).

    Returns 401 with WWW-Authenticate: Bearer header hint. Used by the
    JWT dependency in auth/route handlers.
    """
    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
            details={"WWW-Authenticate": "Bearer"}
        )

class AuthorizationException(AppException):
    """Raised when an authenticated user lacks permission for the requested action.

    Returns 403. Used when, e.g., a user tries to edit another user's post.
    """
    def __init__(self, message: str = "Not enough permissions"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN"
        )

class DatabaseException(AppException):
    """Raised when a database operation fails unexpectedly.

    Returns 500. Used as a generic catch-all for DB errors that should
    not leak implementation details to the client.
    """
    def __init__(self, message: str = "A database error occurred", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR",
            details=details
        )

class ConflictException(AppException):
    """Raised when an action conflicts with the current state (duplicate, race).

    Returns 409. Used when, e.g., a user tries to follow someone they
    already follow, or create a resource that already exists.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            details=details
        )

class RateLimitException(AppException):
    """Raised when a user exceeds the allowed request rate.

    Returns 429. Used by the rate-limiting middleware to signal
    clients they should back off.
    """
    def __init__(self, message: str = "Too many requests"):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED"
        )

class BusinessLogicException(AppException):
    """Raised for domain rule violations that don't fit other categories.

    Returns 400 with a customizable error_code. Used for operation failures
    that aren't purely validation issues, e.g. "cannot share your own post".
    """
    def __init__(self, message: str, error_code: str = "BUSINESS_LOGIC_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=error_code,
            details=details
        )

class WebSocketException(AppException):
    """Raised for WebSocket-specific failures.

    Uses status code 101 (Switching Protocols) as a signal carrier.
    Caught in WebSocket endpoint handlers to send structured error
    frames back through the socket.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_101_SWITCHING_PROTOCOLS,
            error_code="WEBSOCKET_ERROR",
            details=details
        )