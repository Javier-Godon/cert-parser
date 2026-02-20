"""
Test assertions for Result values.

Mirrors Java's ResultAssertions test helper — provides expressive
assert methods that produce clear failure messages.

Usage in tests:
    from railway import ResultAssertions

    def test_create_user():
        result = create_user(valid_command)
        ResultAssertions.assert_success(result)
        assert result.value().name == "Alice"

    def test_invalid_email():
        result = create_user(bad_command)
        ResultAssertions.assert_failure(result, ErrorCode.VALIDATION_ERROR)
        ResultAssertions.assert_failure_message_contains(result, "email")
"""

from __future__ import annotations

from typing import Any, TypeVar

from railway.failure import ErrorCode, FailureDescription
from railway.result import Failure, Result, Success

T = TypeVar("T")


class ResultAssertions:
    """Expressive test assertions for Result values."""

    @staticmethod
    def assert_success(result: Result[T], message: str = "") -> T:
        """
        Assert the Result is a Success and return the value.

        Raises AssertionError with clear message on failure.

            value = ResultAssertions.assert_success(result)
        """
        context = f" — {message}" if message else ""
        assert result.is_success(), (
            f"Expected Success but got Failure("
            f"{result.error().code.value}: {result.error().message!r}){context}"
        )
        return result.value()

    @staticmethod
    def assert_failure(
        result: Result[T],
        expected_code: ErrorCode | None = None,
        message: str = "",
    ) -> FailureDescription:
        """
        Assert the Result is a Failure, optionally checking the error code.

            error = ResultAssertions.assert_failure(result, ErrorCode.VALIDATION_ERROR)
        """
        context = f" — {message}" if message else ""
        assert result.is_failure(), (
            f"Expected Failure but got Success({result.value()!r}){context}"
        )
        error = result.error()
        if expected_code is not None:
            assert error.code == expected_code, (
                f"Expected error code {expected_code.value} "
                f"but got {error.code.value}: {error.message!r}{context}"
            )
        return error

    @staticmethod
    def assert_failure_message_contains(result: Result[T], substring: str) -> None:
        """Assert that the failure message contains the given substring."""
        assert result.is_failure(), (
            f"Expected Failure but got Success({result.value()!r})"
        )
        error = result.error()
        assert substring.lower() in error.message.lower(), (
            f"Expected failure message to contain {substring!r} "
            f"but message was: {error.message!r}"
        )

    @staticmethod
    def assert_failure_message_equals(result: Result[T], expected_message: str) -> None:
        """Assert that the failure message exactly equals the expected message."""
        assert result.is_failure(), (
            f"Expected Failure but got Success({result.value()!r})"
        )
        error = result.error()
        assert error.message == expected_message, (
            f"Expected failure message {expected_message!r} "
            f"but got {error.message!r}"
        )

    @staticmethod
    def assert_success_value(result: Result[T], expected_value: Any) -> None:
        """Assert the Result is a Success with the specific value."""
        value = ResultAssertions.assert_success(result)
        assert value == expected_value, (
            f"Expected success value {expected_value!r} but got {value!r}"
        )
