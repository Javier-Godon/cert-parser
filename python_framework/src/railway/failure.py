"""
Failure description — structured error information for the failure track.

Mirrors Java's FailureResultDescription with ErrorCode enum + metadata.

Python advantage: Enum + frozen dataclass is cleaner than Java records
because dataclass gives us __eq__, __hash__, __repr__ for free, and
Enum members are singleton-comparable with `is`.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, unique
from typing import Optional


@unique
class ErrorCode(Enum):
    """
    Structured error codes for the failure track.

    Organized by HTTP status range for natural REST API mapping:
    - Client errors (4xx): VALIDATION, AUTHENTICATION, AUTHORIZATION, NOT_FOUND, BUSINESS_RULE, RATE_LIMIT
    - Server errors (5xx): TECHNICAL, DATABASE, CONFIGURATION, EXTERNAL_SERVICE, UNAVAILABLE, TIMEOUT, UNKNOWN
    """

    # --- Client-side errors (4xx HTTP range) ---
    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Invalid input format, missing fields, type mismatches (→ 400)."""

    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    """Invalid credentials, expired tokens (→ 401)."""

    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    """Insufficient permissions (→ 403)."""

    NOT_FOUND = "NOT_FOUND"
    """Resource doesn't exist (→ 404)."""

    BUSINESS_RULE_ERROR = "BUSINESS_RULE_ERROR"
    """Domain invariant violated, business constraint failed (→ 409)."""

    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    """Request limits exceeded (→ 429)."""

    # --- Server-side errors (5xx HTTP range) ---
    TECHNICAL_ERROR = "TECHNICAL_ERROR"
    """Infrastructure issues (→ 500)."""

    DATABASE_ERROR = "DATABASE_ERROR"
    """Database connectivity or query failures (→ 500)."""

    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    """System misconfiguration (→ 500)."""

    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    """External API call failures (→ 502)."""

    SERVICE_UNAVAILABLE_ERROR = "SERVICE_UNAVAILABLE_ERROR"
    """Service maintenance or overload (→ 503)."""

    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    """Operation exceeded time limit (→ 504)."""

    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    """Unexpected/unclassified failures (→ 500)."""


@dataclass(frozen=True, slots=True)
class FailureDescription:
    """
    Immutable failure descriptor carrying error code, message, optional exception, and timestamp.

    Mirrors Java's FailureResultDescription record.

    >>> desc = FailureDescription(ErrorCode.VALIDATION_ERROR, "Name is required")
    >>> desc.code
    <ErrorCode.VALIDATION_ERROR: 'VALIDATION_ERROR'>
    >>> desc.message
    'Name is required'
    """

    code: ErrorCode
    message: str
    exception: Optional[BaseException] = field(default=None, repr=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        code: ErrorCode,
        message: str,
        exception: Optional[BaseException] = None,
    ) -> FailureDescription:
        """Factory method matching Java's constructor overloads."""
        return FailureDescription(code=code, message=message, exception=exception)

    def full_stack_trace(self) -> str:
        """
        Full stack trace string including the message and exception chain.

        Mirrors Java's fullStackTrace() method.
        """
        if self.exception is None:
            return self.message
        tb = "".join(traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__))
        return f"{self.message}\n{tb}"
