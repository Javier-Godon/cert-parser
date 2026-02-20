"""
HTTP integration — ErrorCode→HTTP status mapping and response builders.

Framework-agnostic core with optional adapters for FastAPI and Flask.

Mirrors Java's HttpStatusMapper + RailwayResponseBuilder.

Usage (standalone):
    status = HttpStatusMapper.map_error_code(ErrorCode.NOT_FOUND)  # → 404

Usage (FastAPI):
    from railway.http_support import build_fastapi_response
    return build_fastapi_response(result, success_status=201)

Usage (Flask):
    from railway.http_support import build_flask_response
    return build_flask_response(result, success_status=201)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, TypeVar

from railway.failure import ErrorCode, FailureDescription
from railway.result import Result

T = TypeVar("T")


# ──────────────────────── Error Code → HTTP Status Mapping ────────────────────────


class HttpStatusMapper:
    """Maps ErrorCode enum values to HTTP status codes."""

    _CODE_TO_STATUS: dict[ErrorCode, int] = {
        # Client errors (4xx)
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.AUTHENTICATION_ERROR: 401,
        ErrorCode.AUTHORIZATION_ERROR: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.BUSINESS_RULE_ERROR: 409,
        ErrorCode.RATE_LIMIT_ERROR: 429,
        # Server errors (5xx)
        ErrorCode.TECHNICAL_ERROR: 500,
        ErrorCode.DATABASE_ERROR: 500,
        ErrorCode.CONFIGURATION_ERROR: 500,
        ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
        ErrorCode.SERVICE_UNAVAILABLE_ERROR: 503,
        ErrorCode.TIMEOUT_ERROR: 504,
        ErrorCode.UNKNOWN_ERROR: 500,
    }

    _EXCEPTION_TO_STATUS: dict[type, int] = {
        ValueError: 400,
        TypeError: 400,
        KeyError: 400,
        LookupError: 404,
        FileNotFoundError: 404,
        PermissionError: 403,
        TimeoutError: 504,
        ConnectionError: 503,
        NotImplementedError: 501,
    }

    @classmethod
    def map_error_code(cls, code: ErrorCode) -> int:
        """Map an ErrorCode to an HTTP status code."""
        return cls._CODE_TO_STATUS.get(code, 500)

    @classmethod
    def map_failure(cls, failure: FailureDescription) -> int:
        """Map a FailureDescription to an HTTP status code (considers both code and exception)."""
        return cls._CODE_TO_STATUS.get(failure.code, 500)

    @classmethod
    def map_exception(cls, exception: BaseException) -> int:
        """Map a Python exception to an HTTP status code."""
        for exc_type, status in cls._EXCEPTION_TO_STATUS.items():
            if isinstance(exception, exc_type):
                return status
        return 500


# ──────────────────────── Error Response DTO ────────────────────────


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    """
    Standardized error response body.

    Mirrors Java's ErrorResponse record.

        {
            "error_code": "VALIDATION_ERROR",
            "message": "Name is required",
            "timestamp": "2026-02-17T10:30:00+00:00"
        }
    """

    error_code: str
    message: str
    timestamp: str

    @staticmethod
    def from_failure(failure: FailureDescription) -> ErrorResponse:
        return ErrorResponse(
            error_code=failure.code.value,
            message=failure.message,
            timestamp=failure.timestamp.isoformat(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# ──────────────────────── Generic Response Builder ────────────────────────


def build_response(
    result: Result[T],
    success_status: int = 200,
    success_body: Any = None,
) -> tuple[Any, int]:
    """
    Build a (body, status_code) tuple from a Result.

    Framework-agnostic — works with any web framework.

        body, status = build_response(result, success_status=201)
    """
    return result.either(
        on_success=lambda value: (
            success_body if success_body is not None else value,
            success_status,
        ),
        on_failure=lambda error: (
            ErrorResponse.from_failure(error).to_dict(),
            HttpStatusMapper.map_failure(error),
        ),
    )


# ──────────────────────── FastAPI Adapter ────────────────────────


def build_fastapi_response(
    result: Result[T],
    success_status: int = 200,
) -> Any:
    """
    Build a FastAPI JSONResponse from a Result.

    Requires fastapi to be installed.

        @app.post("/users", status_code=201)
        def create_user(request: CreateUserRequest):
            result = handler.handle(request.to_command())
            return build_fastapi_response(result, success_status=201)
    """
    try:
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError("FastAPI is required: pip install railway-rop[fastapi]")

    body, status = build_response(result, success_status)
    return JSONResponse(content=body, status_code=status)


# ──────────────────────── Flask Adapter ────────────────────────


def build_flask_response(
    result: Result[T],
    success_status: int = 200,
) -> Any:
    """
    Build a Flask response from a Result.

    Requires flask to be installed.

        @app.route("/users", methods=["POST"])
        def create_user():
            result = handler.handle(request.get_json())
            return build_flask_response(result, success_status=201)
    """
    try:
        from flask import jsonify
    except ImportError:
        raise ImportError("Flask is required: pip install railway-rop[flask]")

    body, status = build_response(result, success_status)
    return jsonify(body), status
