"""Tests for ResultFailures convenience factories."""

import pytest

from railway import ErrorCode, Result
from railway.result_failures import ResultFailures


class TestConvenienceFactories:
    def test_validation_error(self):
        result = ResultFailures.validation_error("Name is required")
        assert result.is_failure()
        assert result.error().code == ErrorCode.VALIDATION_ERROR
        assert result.error().message == "Name is required"

    def test_business_rule_error(self):
        result = ResultFailures.business_rule_error("Insufficient stock")
        assert result.error().code == ErrorCode.BUSINESS_RULE_ERROR

    def test_not_found(self):
        result = ResultFailures.not_found("User", "user-123")
        assert result.error().code == ErrorCode.NOT_FOUND
        assert "User" in result.error().message
        assert "user-123" in result.error().message

    def test_authentication_error(self):
        result = ResultFailures.authentication_error("Token expired")
        assert result.error().code == ErrorCode.AUTHENTICATION_ERROR

    def test_authorization_error(self):
        result = ResultFailures.authorization_error("Insufficient permissions")
        assert result.error().code == ErrorCode.AUTHORIZATION_ERROR

    def test_database_error(self):
        ex = ConnectionError("connection refused")
        result = ResultFailures.database_error("Query failed", ex)
        assert result.error().code == ErrorCode.DATABASE_ERROR
        assert result.error().exception is ex

    def test_technical_error(self):
        result = ResultFailures.technical_error("Disk full")
        assert result.error().code == ErrorCode.TECHNICAL_ERROR

    def test_external_service_error(self):
        result = ResultFailures.external_service_error("API timeout")
        assert result.error().code == ErrorCode.EXTERNAL_SERVICE_ERROR

    def test_timeout_error(self):
        result = ResultFailures.timeout_error("Exceeded 30s")
        assert result.error().code == ErrorCode.TIMEOUT_ERROR

    def test_configuration_error(self):
        result = ResultFailures.configuration_error("Missing DB_URL")
        assert result.error().code == ErrorCode.CONFIGURATION_ERROR


class TestExceptionMapping:
    def test_value_error_maps_to_validation(self):
        result = ResultFailures.from_exception("bad input", ValueError("x"))
        assert result.error().code == ErrorCode.VALIDATION_ERROR

    def test_type_error_maps_to_validation(self):
        result = ResultFailures.from_exception("wrong type", TypeError("x"))
        assert result.error().code == ErrorCode.VALIDATION_ERROR

    def test_key_error_maps_to_validation(self):
        result = ResultFailures.from_exception("missing key", KeyError("name"))
        assert result.error().code == ErrorCode.VALIDATION_ERROR

    def test_lookup_error_maps_to_not_found(self):
        result = ResultFailures.from_exception("not found", LookupError("x"))
        assert result.error().code == ErrorCode.NOT_FOUND

    def test_file_not_found_maps_to_not_found(self):
        result = ResultFailures.from_exception("no file", FileNotFoundError("x"))
        assert result.error().code == ErrorCode.NOT_FOUND

    def test_permission_error_maps_to_authorization(self):
        result = ResultFailures.from_exception("denied", PermissionError("x"))
        assert result.error().code == ErrorCode.AUTHORIZATION_ERROR

    def test_timeout_error_maps_to_timeout(self):
        result = ResultFailures.from_exception("slow", TimeoutError("x"))
        assert result.error().code == ErrorCode.TIMEOUT_ERROR

    def test_connection_error_maps_to_external_service(self):
        result = ResultFailures.from_exception("offline", ConnectionError("x"))
        assert result.error().code == ErrorCode.EXTERNAL_SERVICE_ERROR

    def test_unknown_exception_maps_to_unknown(self):
        result = ResultFailures.from_exception("wat", RuntimeError("x"))
        assert result.error().code == ErrorCode.UNKNOWN_ERROR

    def test_from_exception_auto(self):
        result = ResultFailures.from_exception_auto(ValueError("bad value"))
        assert result.error().code == ErrorCode.VALIDATION_ERROR
        assert result.error().message == "bad value"
