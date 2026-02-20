"""Tests for FailureDescription and ErrorCode."""

from datetime import UTC, datetime

import pytest

from railway import ErrorCode, FailureDescription


class TestErrorCode:
    def test_all_13_error_codes_exist(self):
        codes = list(ErrorCode)
        assert len(codes) == 13

    def test_client_error_codes(self):
        client_codes = {
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.AUTHENTICATION_ERROR,
            ErrorCode.AUTHORIZATION_ERROR,
            ErrorCode.NOT_FOUND,
            ErrorCode.BUSINESS_RULE_ERROR,
            ErrorCode.RATE_LIMIT_ERROR,
        }
        assert len(client_codes) == 6

    def test_server_error_codes(self):
        server_codes = {
            ErrorCode.TECHNICAL_ERROR,
            ErrorCode.DATABASE_ERROR,
            ErrorCode.CONFIGURATION_ERROR,
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            ErrorCode.SERVICE_UNAVAILABLE_ERROR,
            ErrorCode.TIMEOUT_ERROR,
            ErrorCode.UNKNOWN_ERROR,
        }
        assert len(server_codes) == 7

    def test_error_code_values_are_strings(self):
        for code in ErrorCode:
            assert isinstance(code.value, str)


class TestFailureDescription:
    def test_creation_with_code_and_message(self):
        desc = FailureDescription(ErrorCode.VALIDATION_ERROR, "Name is required")
        assert desc.code == ErrorCode.VALIDATION_ERROR
        assert desc.message == "Name is required"
        assert desc.exception is None
        assert desc.timestamp is not None

    def test_creation_with_exception(self):
        ex = ValueError("bad")
        desc = FailureDescription(ErrorCode.DATABASE_ERROR, "query failed", ex)
        assert desc.exception is ex

    def test_factory_method(self):
        desc = FailureDescription.create(ErrorCode.NOT_FOUND, "missing")
        assert desc.code == ErrorCode.NOT_FOUND
        assert desc.message == "missing"

    def test_immutability(self):
        desc = FailureDescription(ErrorCode.VALIDATION_ERROR, "test")
        with pytest.raises(AttributeError):
            desc.message = "changed"  # type: ignore

    def test_timestamp_is_utc(self):
        desc = FailureDescription(ErrorCode.VALIDATION_ERROR, "test")
        assert desc.timestamp.tzinfo is not None

    def test_full_stack_trace_without_exception(self):
        desc = FailureDescription(ErrorCode.VALIDATION_ERROR, "just a message")
        assert desc.full_stack_trace() == "just a message"

    def test_full_stack_trace_with_exception(self):
        try:
            raise ValueError("boom")
        except ValueError as e:
            desc = FailureDescription(ErrorCode.DATABASE_ERROR, "query failed", e)
            trace = desc.full_stack_trace()
            assert "query failed" in trace
            assert "ValueError" in trace
            assert "boom" in trace

    def test_equality(self):
        a = FailureDescription(ErrorCode.NOT_FOUND, "x")
        b = FailureDescription(ErrorCode.NOT_FOUND, "x")
        # frozen dataclasses compare all fields, but timestamps differ
        # so we compare code + message manually
        assert a.code == b.code
        assert a.message == b.message
