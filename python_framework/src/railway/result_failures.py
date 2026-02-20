"""
Convenience factory methods for common Result failures.

Mirrors Java's ResultFailures utility class — eliminates boilerplate
for the most frequent error types.

Usage:
    from railway.result_failures import ResultFailures

    # Instead of:
    Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")

    # Write:
    ResultFailures.validation_error("Name is required")
"""

from __future__ import annotations

from typing import TypeVar

from railway.failure import ErrorCode, FailureDescription
from railway.result import Result

T = TypeVar("T")


class ResultFailures:
    """
    Factory methods for common failure types.

    Maps 1:1 to Java's ResultFailures utility class, plus Python-specific
    exception mapping.
    """

    @staticmethod
    def validation_error(message: str) -> Result:
        """Invalid input — missing fields, wrong format, type mismatch."""
        return Result.failure(ErrorCode.VALIDATION_ERROR, message)

    @staticmethod
    def business_rule_error(message: str) -> Result:
        """Domain invariant violated — business constraint failed."""
        return Result.failure(ErrorCode.BUSINESS_RULE_ERROR, message)

    @staticmethod
    def not_found(resource_type: str, identifier: str) -> Result:
        """Resource doesn't exist."""
        return Result.failure(
            ErrorCode.NOT_FOUND,
            f"{resource_type} not found with identifier: {identifier}",
        )

    @staticmethod
    def authentication_error(message: str) -> Result:
        """Invalid credentials or expired token."""
        return Result.failure(ErrorCode.AUTHENTICATION_ERROR, message)

    @staticmethod
    def authorization_error(message: str) -> Result:
        """Insufficient permissions."""
        return Result.failure(ErrorCode.AUTHORIZATION_ERROR, message)

    @staticmethod
    def database_error(message: str, exception: BaseException | None = None) -> Result:
        """Database connectivity or query failure."""
        return Result.failure(ErrorCode.DATABASE_ERROR, message, exception)

    @staticmethod
    def technical_error(message: str, exception: BaseException | None = None) -> Result:
        """Infrastructure issue."""
        return Result.failure(ErrorCode.TECHNICAL_ERROR, message, exception)

    @staticmethod
    def external_service_error(message: str, exception: BaseException | None = None) -> Result:
        """External API call failure."""
        return Result.failure(ErrorCode.EXTERNAL_SERVICE_ERROR, message, exception)

    @staticmethod
    def timeout_error(message: str) -> Result:
        """Operation exceeded time limit."""
        return Result.failure(ErrorCode.TIMEOUT_ERROR, message)

    @staticmethod
    def configuration_error(message: str) -> Result:
        """System misconfiguration."""
        return Result.failure(ErrorCode.CONFIGURATION_ERROR, message)

    @staticmethod
    def from_exception(message: str, exception: BaseException) -> Result:
        """
        Auto-map a Python exception to the appropriate ErrorCode.

        Mirrors Java's ExceptionToErrorCodeMapper.

        Mapping:
          - ValueError, TypeError, KeyError → VALIDATION_ERROR
          - LookupError, FileNotFoundError → NOT_FOUND
          - PermissionError → AUTHORIZATION_ERROR
          - TimeoutError → TIMEOUT_ERROR
          - ConnectionError, OSError → EXTERNAL_SERVICE_ERROR
          - Everything else → UNKNOWN_ERROR
        """
        code = _map_exception_to_code(exception)
        return Result.failure(code, message, exception)

    @staticmethod
    def from_exception_auto(exception: BaseException) -> Result:
        """Map exception using its own message."""
        code = _map_exception_to_code(exception)
        return Result.failure(code, str(exception), exception)


def _map_exception_to_code(exception: BaseException) -> ErrorCode:
    """Map a Python exception type to the most appropriate ErrorCode."""
    match exception:
        case ValueError() | TypeError() | KeyError():
            return ErrorCode.VALIDATION_ERROR
        case LookupError() | FileNotFoundError():
            return ErrorCode.NOT_FOUND
        case PermissionError():
            return ErrorCode.AUTHORIZATION_ERROR
        case TimeoutError():
            return ErrorCode.TIMEOUT_ERROR
        case ConnectionError() | OSError():
            return ErrorCode.EXTERNAL_SERVICE_ERROR
        case _:
            return ErrorCode.UNKNOWN_ERROR
