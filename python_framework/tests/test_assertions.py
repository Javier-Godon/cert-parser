"""Tests for ResultAssertions test helper."""

import pytest

from railway import ErrorCode, Result, ResultAssertions


class TestAssertSuccess:
    def test_passes_on_success(self):
        value = ResultAssertions.assert_success(Result.success(42))
        assert value == 42

    def test_fails_on_failure_with_clear_message(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
        with pytest.raises(AssertionError, match="Expected Success but got Failure"):
            ResultAssertions.assert_success(result)

    def test_custom_message(self):
        result = Result.failure(ErrorCode.NOT_FOUND, "x")
        with pytest.raises(AssertionError, match="custom context"):
            ResultAssertions.assert_success(result, "custom context")


class TestAssertFailure:
    def test_passes_on_failure(self):
        error = ResultAssertions.assert_failure(
            Result.failure(ErrorCode.NOT_FOUND, "missing")
        )
        assert error.code == ErrorCode.NOT_FOUND

    def test_checks_error_code(self):
        error = ResultAssertions.assert_failure(
            Result.failure(ErrorCode.VALIDATION_ERROR, "bad"),
            ErrorCode.VALIDATION_ERROR,
        )
        assert error.message == "bad"

    def test_fails_on_wrong_error_code(self):
        result = Result.failure(ErrorCode.NOT_FOUND, "x")
        with pytest.raises(AssertionError, match="Expected error code VALIDATION_ERROR"):
            ResultAssertions.assert_failure(result, ErrorCode.VALIDATION_ERROR)

    def test_fails_on_success(self):
        with pytest.raises(AssertionError, match="Expected Failure but got Success"):
            ResultAssertions.assert_failure(Result.success(42))


class TestAssertFailureMessage:
    def test_contains_substring(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
        ResultAssertions.assert_failure_message_contains(result, "name")

    def test_case_insensitive(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "NAME IS REQUIRED")
        ResultAssertions.assert_failure_message_contains(result, "name")

    def test_fails_when_not_contained(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "Age is required")
        with pytest.raises(AssertionError, match="Expected failure message to contain"):
            ResultAssertions.assert_failure_message_contains(result, "name")

    def test_exact_match(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "exact message")
        ResultAssertions.assert_failure_message_equals(result, "exact message")

    def test_exact_match_fails(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "actual")
        with pytest.raises(AssertionError, match="Expected failure message"):
            ResultAssertions.assert_failure_message_equals(result, "expected")


class TestAssertSuccessValue:
    def test_exact_value_match(self):
        ResultAssertions.assert_success_value(Result.success(42), 42)

    def test_fails_on_wrong_value(self):
        with pytest.raises(AssertionError, match="Expected success value"):
            ResultAssertions.assert_success_value(Result.success(42), 99)

    def test_fails_on_failure(self):
        with pytest.raises(AssertionError, match="Expected Success"):
            ResultAssertions.assert_success_value(
                Result.failure(ErrorCode.NOT_FOUND, "x"), 42
            )
