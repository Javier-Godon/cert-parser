"""
Unit tests for the HTTP adapter — dual-token authentication and binary download.

TDD RED phase — these tests are written BEFORE the implementation.
Uses respx to mock httpx HTTP calls (never makes real HTTP requests).

Tests cover the 3-endpoint authentication flow:
  1. HttpAccessTokenProvider: OpenID Connect password grant → access_token
  2. HttpSfcTokenProvider: SFC login with bearer + JSON body → sfc_token
  3. HttpBinaryDownloader: Download with dual-token headers → .bin file

Test categories per adapter:
  - Success: correct response → Result.success
  - Auth failure: 401/403 → Result.failure(AUTHENTICATION_ERROR)
  - Server error: 500 → Result.failure
  - Timeout/network: → Result.failure (never raises)
  - Malformed response: → Result.failure (never raises)
"""

from __future__ import annotations

import httpx
import pytest
import respx
from railway import ErrorCode, ResultAssertions

from cert_parser.adapters.http_client import (
    HttpAccessTokenProvider,
    HttpBinaryDownloader,
    HttpSfcTokenProvider,
)
from cert_parser.domain.models import AuthCredentials

# ─────────────────────── Fixtures ───────────────────────

AUTH_URL = "https://auth.example.com/protocol/openid-connect/token"
LOGIN_URL = "https://api.example.com/auth/v1/login"
DOWNLOAD_URL = "https://api.example.com/certificates/csca"
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
USERNAME = "test-user"
PASSWORD = "test-password"
BORDER_POST_ID = 42
BOX_ID = 7
PASSENGER_CONTROL_TYPE = 1


@pytest.fixture()
def access_token_provider() -> HttpAccessTokenProvider:
    """Create an HttpAccessTokenProvider with test credentials."""
    return HttpAccessTokenProvider(
        auth_url=AUTH_URL,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        username=USERNAME,
        password=PASSWORD,
        timeout=5,
    )


@pytest.fixture()
def sfc_token_provider() -> HttpSfcTokenProvider:
    """Create an HttpSfcTokenProvider with test configuration."""
    return HttpSfcTokenProvider(
        login_url=LOGIN_URL,
        border_post_id=BORDER_POST_ID,
        box_id=BOX_ID,
        passenger_control_type=PASSENGER_CONTROL_TYPE,
        timeout=5,
    )


@pytest.fixture()
def downloader() -> HttpBinaryDownloader:
    """Create an HttpBinaryDownloader with test URL."""
    return HttpBinaryDownloader(
        download_url=DOWNLOAD_URL,
        timeout=5,
    )


# ═══════════════════════════════════════════════════════════════════════
# Access Token Provider (Step 1 — OpenID Connect password grant)
# ═══════════════════════════════════════════════════════════════════════


class TestAccessTokenSuccess:
    """
    GIVEN valid OAuth2 password grant credentials
    WHEN the OpenID Connect server returns 200 with a valid access_token
    THEN acquire_token returns Result.success(token_string).
    """

    @respx.mock
    def test_returns_success_with_token(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN auth server responds 200 with {"access_token": "abc123"}
        WHEN acquire_token is called
        THEN it returns Success("abc123").
        """
        respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"access_token": "abc123"}))
        result = access_token_provider.acquire_token()
        token = ResultAssertions.assert_success(result)
        assert token == "abc123"

    @respx.mock
    def test_sends_password_grant_credentials(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN a configured access token provider
        WHEN acquire_token is called
        THEN it POSTs with grant_type=password, client_id, client_secret, username, password.
        """
        route = respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "token"})
        )
        access_token_provider.acquire_token()
        assert route.called
        request = route.calls.last.request
        body = request.content.decode()
        assert "grant_type=password" in body
        assert CLIENT_ID in body
        assert CLIENT_SECRET in body
        assert USERNAME in body
        assert PASSWORD in body


class TestAccessTokenAuthFailure:
    """
    GIVEN invalid credentials
    WHEN the OpenID Connect server returns 401 or 403
    THEN acquire_token returns Result.failure(AUTHENTICATION_ERROR).
    """

    @respx.mock
    def test_401_returns_authentication_error(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN auth server responds 401
        WHEN acquire_token is called
        THEN it returns Failure(AUTHENTICATION_ERROR).
        """
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )
        result = access_token_provider.acquire_token()
        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)

    @respx.mock
    def test_403_returns_authentication_error(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN auth server responds 403
        WHEN acquire_token is called
        THEN it returns Failure(AUTHENTICATION_ERROR).
        """
        respx.post(AUTH_URL).mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        result = access_token_provider.acquire_token()
        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestAccessTokenServerError:
    """
    GIVEN the OpenID Connect server is experiencing errors
    WHEN acquire_token is called
    THEN it returns Result.failure(AUTHENTICATION_ERROR).
    """

    @respx.mock
    def test_500_returns_failure(self, access_token_provider: HttpAccessTokenProvider) -> None:
        """
        GIVEN auth server responds 500
        WHEN acquire_token is called
        THEN it returns Failure.
        """
        respx.post(AUTH_URL).mock(return_value=httpx.Response(500))
        result = access_token_provider.acquire_token()
        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestAccessTokenTimeout:
    """
    GIVEN the OpenID Connect server does not respond in time
    WHEN acquire_token is called
    THEN it returns Result.failure (never raises).
    """

    @respx.mock
    def test_timeout_returns_failure(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN auth server times out
        WHEN acquire_token is called
        THEN it returns Failure (does not raise).
        """
        respx.post(AUTH_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
        result = access_token_provider.acquire_token()
        assert result.is_failure()


class TestAccessTokenMalformedResponse:
    """
    GIVEN the OpenID Connect server returns 200 but malformed JSON
    WHEN acquire_token is called
    THEN it returns Result.failure (never raises).
    """

    @respx.mock
    def test_missing_access_token_returns_failure(
        self, access_token_provider: HttpAccessTokenProvider
    ) -> None:
        """
        GIVEN 200 with JSON missing access_token key
        WHEN acquire_token is called
        THEN it returns Failure.
        """
        respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"token_type": "bearer"}))
        result = access_token_provider.acquire_token()
        assert result.is_failure()


# ═══════════════════════════════════════════════════════════════════════
# SFC Token Provider (Step 2 — SFC login with bearer + JSON body)
# ═══════════════════════════════════════════════════════════════════════


class TestSfcTokenSuccess:
    """
    GIVEN a valid access_token and border post configuration
    WHEN the SFC login server returns 200 with an SFC token
    THEN acquire_token returns Result.success(sfc_token_string).
    """

    @respx.mock
    def test_returns_success_with_sfc_token(
        self, sfc_token_provider: HttpSfcTokenProvider
    ) -> None:
        """
        GIVEN login server responds 200 with SFC token in body
        WHEN acquire_token("access-token") is called
        THEN it returns Success(sfc_token).
        """
        respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, text="sfc-token-xyz"))
        result = sfc_token_provider.acquire_token("access-token")
        sfc_token = ResultAssertions.assert_success(result)
        assert sfc_token == "sfc-token-xyz"

    @respx.mock
    def test_sends_bearer_token_and_json_body(
        self, sfc_token_provider: HttpSfcTokenProvider
    ) -> None:
        """
        GIVEN a configured SFC token provider
        WHEN acquire_token("my-access") is called
        THEN it POSTs with Authorization: Bearer my-access and JSON body with border post config.
        """
        route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, text="sfc"))
        sfc_token_provider.acquire_token("my-access")
        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer my-access"
        import json

        body = json.loads(request.content)
        assert body["borderPostId"] == BORDER_POST_ID
        assert body["boxId"] == BOX_ID
        assert body["passengerControlType"] == PASSENGER_CONTROL_TYPE


class TestSfcTokenAuthFailure:
    """
    GIVEN an expired or invalid access_token
    WHEN the SFC login server returns 401
    THEN acquire_token returns Result.failure(AUTHENTICATION_ERROR).
    """

    @respx.mock
    def test_401_returns_authentication_error(
        self, sfc_token_provider: HttpSfcTokenProvider
    ) -> None:
        """
        GIVEN login server responds 401
        WHEN acquire_token is called
        THEN it returns Failure(AUTHENTICATION_ERROR).
        """
        respx.post(LOGIN_URL).mock(return_value=httpx.Response(401))
        result = sfc_token_provider.acquire_token("expired-token")
        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestSfcTokenServerError:
    """
    GIVEN the SFC login server is experiencing errors
    WHEN acquire_token is called
    THEN it returns Result.failure(AUTHENTICATION_ERROR).
    """

    @respx.mock
    def test_500_returns_failure(self, sfc_token_provider: HttpSfcTokenProvider) -> None:
        """
        GIVEN login server responds 500
        WHEN acquire_token is called
        THEN it returns Failure.
        """
        respx.post(LOGIN_URL).mock(return_value=httpx.Response(500))
        result = sfc_token_provider.acquire_token("token")
        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestSfcTokenTimeout:
    """
    GIVEN the SFC login server does not respond in time
    WHEN acquire_token is called
    THEN it returns Result.failure (never raises).
    """

    @respx.mock
    def test_timeout_returns_failure(self, sfc_token_provider: HttpSfcTokenProvider) -> None:
        """
        GIVEN login server times out
        WHEN acquire_token is called
        THEN it returns Failure (does not raise).
        """
        respx.post(LOGIN_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
        result = sfc_token_provider.acquire_token("token")
        assert result.is_failure()


# ═══════════════════════════════════════════════════════════════════════
# Binary Download (Step 3 — dual-token authentication)
# ═══════════════════════════════════════════════════════════════════════


class TestBinaryDownloadSuccess:
    """
    GIVEN valid AuthCredentials with both tokens
    WHEN the download server returns 200 with binary content
    THEN download returns Result.success(bytes).
    """

    @respx.mock
    def test_returns_success_with_bytes(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN download server responds 200 with binary body
        WHEN download(credentials) is called
        THEN it returns Success(binary_content).
        """
        content = b"\x30\x82\x01\x00" + b"\x00" * 252
        credentials = AuthCredentials(access_token="at", sfc_token="sfc")
        respx.get(DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=content))
        result = downloader.download(credentials)
        data = ResultAssertions.assert_success(result)
        assert data == content

    @respx.mock
    def test_sends_dual_token_headers(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN AuthCredentials(access_token="at", sfc_token="sfc")
        WHEN download(credentials) is called
        THEN it sends Authorization: Bearer at AND x-sfc-authorization: Bearer sfc.
        """
        credentials = AuthCredentials(access_token="at", sfc_token="sfc")
        route = respx.get(DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=b"data"))
        downloader.download(credentials)
        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer at"
        assert request.headers["x-sfc-authorization"] == "Bearer sfc"


class TestBinaryDownloadAuthFailure:
    """
    GIVEN an expired or invalid token
    WHEN the download server returns 401
    THEN download returns Result.failure(EXTERNAL_SERVICE_ERROR).
    """

    @respx.mock
    def test_401_returns_failure(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN download server responds 401
        WHEN download is called
        THEN it returns Failure(EXTERNAL_SERVICE_ERROR).
        """
        credentials = AuthCredentials(access_token="expired", sfc_token="expired")
        respx.get(DOWNLOAD_URL).mock(return_value=httpx.Response(401))
        result = downloader.download(credentials)
        ResultAssertions.assert_failure(result, ErrorCode.EXTERNAL_SERVICE_ERROR)


class TestBinaryDownloadServerError:
    """
    GIVEN the download server is experiencing errors
    WHEN download is called
    THEN it returns Result.failure(EXTERNAL_SERVICE_ERROR).
    """

    @respx.mock
    def test_500_returns_failure(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN download server responds 500
        WHEN download is called
        THEN it returns Failure(EXTERNAL_SERVICE_ERROR).
        """
        credentials = AuthCredentials(access_token="at", sfc_token="sfc")
        respx.get(DOWNLOAD_URL).mock(return_value=httpx.Response(500))
        result = downloader.download(credentials)
        ResultAssertions.assert_failure(result, ErrorCode.EXTERNAL_SERVICE_ERROR)


class TestBinaryDownloadTimeout:
    """
    GIVEN the download server does not respond in time
    WHEN download is called
    THEN it returns Result.failure (never raises).
    """

    @respx.mock
    def test_timeout_returns_failure(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN download server times out
        WHEN download is called
        THEN it returns Failure (does not raise).
        """
        credentials = AuthCredentials(access_token="at", sfc_token="sfc")
        respx.get(DOWNLOAD_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
        result = downloader.download(credentials)
        assert result.is_failure()


class TestBinaryDownloadNetworkError:
    """
    GIVEN a network connectivity failure
    WHEN download is called
    THEN it returns Result.failure (never raises).
    """

    @respx.mock
    def test_network_error_returns_failure(self, downloader: HttpBinaryDownloader) -> None:
        """
        GIVEN network connection fails
        WHEN download is called
        THEN it returns Failure.
        """
        credentials = AuthCredentials(access_token="at", sfc_token="sfc")
        respx.get(DOWNLOAD_URL).mock(side_effect=httpx.ConnectError("connection refused"))
        result = downloader.download(credentials)
        assert result.is_failure()
