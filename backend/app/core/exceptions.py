"""Domain exceptions and standardized JSON exception handlers."""

from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, get_request_id

logger = get_logger("exceptions")


class AppException(Exception):
    """Base domain exception for application errors."""

    def __init__(
        self,
        message: str = "An error occurred",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "APP_ERROR",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class BadRequestException(AppException):
    """Exception for malformed or invalid business requests."""

    def __init__(
        self,
        message: str = "Bad request",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BAD_REQUEST",
            details=details,
        )


class UnauthorizedException(AppException):
    """Exception for missing or invalid authentication credentials."""

    def __init__(
        self,
        message: str = "Authentication required",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenException(AppException):
    """Exception for lack of required permissions."""

    def __init__(
        self,
        message: str = "Permission denied",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
            details=details,
        )


class NotFoundException(AppException):
    """Exception for nonexistent domain entities."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            details=details,
        )


class ConflictException(AppException):
    """Exception for state or resource conflicts."""

    def __init__(
        self,
        message: str = "Resource conflict",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            details=details,
        )


class InsufficientBalanceException(AppException):
    """Exception when a user attempts a wager without sufficient virtual credits."""

    def __init__(
        self,
        message: str = "Insufficient virtual credits",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INSUFFICIENT_FUNDS",
            details=details,
        )


class IdempotencyException(AppException):
    """Exception for duplicate idempotency key reuse or lock contention."""

    def __init__(
        self,
        message: str = "Idempotency key already processed or locked",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="IDEMPOTENCY_CONFLICT",
            details=details,
        )


class RateLimitException(AppException):
    """Exception when a client exceeds rate limits."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
        )


class ServiceUnavailableException(AppException):
    """Exception when a critical dependency or service is unreachable."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="SERVICE_UNAVAILABLE",
            details=details,
        )


def _build_error_payload(
    code: str,
    message: str,
    details: Optional[Any] = None,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": request_id,
    }


async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application domain exceptions."""
    req_id = get_request_id()
    logger.warning(
        "Application exception caught",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
            request_id=req_id,
        ),
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI / Pydantic schema validation errors."""
    req_id = get_request_id()
    # mode='json' ensures all Pydantic v2-specific types (PydanticUrl, etc.) are
    # converted to plain Python objects that JSONResponse can serialize.
    try:
        errors = exc.errors(include_url=False)
    except TypeError:
        errors = exc.errors()

    # Sanitize: convert any remaining non-serializable objects to str
    import json

    def _safe(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_safe(i) for i in obj]
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    safe_errors = _safe(errors)

    logger.warning("Request validation failed", error_count=len(safe_errors))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_build_error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=safe_errors,
            request_id=req_id,
        ),
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette HTTP exceptions (e.g. 404, 405)."""
    req_id = get_request_id()
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            details=None,
            request_id=req_id,
        ),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors."""
    req_id = get_request_id()
    logger.exception("Unhandled server exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_payload(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred",
            details=None,
            request_id=req_id,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore


class SecondFactorRequiredException(UnauthorizedException):
    """Password was right; a one-time code was sent / is still needed.

    Not a failed login, so it must not count towards the lockout counter.
    """
