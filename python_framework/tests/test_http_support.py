"""Tests for HTTP integration — status mapping and response builders."""

import pytest

from railway import ErrorCode, FailureDescription, Result
from railway.http_support import HttpStatusMapper, ErrorResponse, build_response


class TestHttpStatusMapper:
    @pytest.mark.parametrize(
        "code,expected_status",
        [
            (ErrorCode.VALIDATION_ERROR, 400),
            (ErrorCode.AUTHENTICATION_ERROR, 401),
            (ErrorCode.AUTHORIZATION_ERROR, 403),
            (ErrorCode.NOT_FOUND, 404),
            (ErrorCode.BUSINESS_RULE_ERROR, 409),
            (ErrorCode.RATE_LIMIT_ERROR, 429),
            (ErrorCode.TECHNICAL_ERROR, 500),
            (ErrorCode.DATABASE_ERROR, 500),
            (ErrorCode.CONFIGURATION_ERROR, 500),
            (ErrorCode.EXTERNAL_SERVICE_ERROR, 502),
            (ErrorCode.SERVICE_UNAVAILABLE_ERROR, 503),
            (ErrorCode.TIMEOUT_ERROR, 504),
            (ErrorCode.UNKNOWN_ERROR, 500),
        ],
    )
    def test_error_code_to_http_status(self, code, expected_status):
        assert HttpStatusMapper.map_error_code(code) == expected_status

    def test_map_failure_description(self):
        failure = FailureDescription(ErrorCode.NOT_FOUND, "missing")
        assert HttpStatusMapper.map_failure(failure) == 404

    @pytest.mark.parametrize(
        "exception_type,expected_status",
        [
            (ValueError, 400),
            (TypeError, 400),
            (KeyError, 400),
            (LookupError, 404),
            (FileNotFoundError, 404),
            (PermissionError, 403),
            (TimeoutError, 504),
            (ConnectionError, 503),
            (NotImplementedError, 501),
        ],
    )
    def test_exception_to_http_status(self, exception_type, expected_status):
        assert HttpStatusMapper.map_exception(exception_type("test")) == expected_status

    def test_unknown_exception_maps_to_500(self):
        assert HttpStatusMapper.map_exception(RuntimeError("x")) == 500


class TestErrorResponse:
    def test_from_failure(self):
        failure = FailureDescription(ErrorCode.VALIDATION_ERROR, "bad input")
        response = ErrorResponse.from_failure(failure)
        assert response.error_code == "VALIDATION_ERROR"
        assert response.message == "bad input"
        assert response.timestamp is not None

    def test_to_dict(self):
        failure = FailureDescription(ErrorCode.NOT_FOUND, "missing")
        d = ErrorResponse.from_failure(failure).to_dict()
        assert d["error_code"] == "NOT_FOUND"
        assert d["message"] == "missing"
        assert "timestamp" in d


class TestBuildResponse:
    def test_success_response(self):
        body, status = build_response(Result.success({"id": 1, "name": "Alice"}))
        assert status == 200
        assert body == {"id": 1, "name": "Alice"}

    def test_success_with_custom_status(self):
        body, status = build_response(Result.success({"id": 1}), success_status=201)
        assert status == 201

    def test_failure_response(self):
        result = Result.failure(ErrorCode.NOT_FOUND, "User not found")
        body, status = build_response(result)
        assert status == 404
        assert body["error_code"] == "NOT_FOUND"
        assert body["message"] == "User not found"

    def test_validation_error_response(self):
        result = Result.failure(ErrorCode.VALIDATION_ERROR, "Name is required")
        body, status = build_response(result)
        assert status == 400

    def test_server_error_response(self):
        result = Result.failure(ErrorCode.DATABASE_ERROR, "Connection refused")
        body, status = build_response(result)
        assert status == 500
