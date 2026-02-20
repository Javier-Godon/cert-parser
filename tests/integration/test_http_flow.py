"""
Integration tests for the 3-endpoint HTTP authentication and download flow.

Simulates the real REST services using respx (like WireMock in Java):
  1. OpenID Connect token endpoint (password grant)
  2. SFC login endpoint (bearer + JSON body)
  3. Certificate download endpoint (dual-token headers)

These tests exercise the full HTTP adapter chain end-to-end
without making real HTTP calls. They verify that the adapters
correctly orchestrate the 3-endpoint flow when wired together.

Each test follows Given/When/Then BDD structure.
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

# ─────────────────────── Service URLs (simulated) ───────────────────────

AUTH_URL = "https://keycloak.example.com/realms/app/protocol/openid-connect/token"
LOGIN_URL = "https://api.example.com/auth/v1/login"
DOWNLOAD_URL = "https://api.example.com/certificates/csca"

# ─────────────────────── Fixtures ───────────────────────


@pytest.fixture()
def access_provider() -> HttpAccessTokenProvider:
    """Access token provider configured for simulated Keycloak."""
    return HttpAccessTokenProvider(
        auth_url=AUTH_URL,
        client_id="cert-parser-client",
        client_secret="super-secret-123",
        username="operator@border.gov",
        password="operator-pass",
        timeout=5,
    )


@pytest.fixture()
def sfc_provider() -> HttpSfcTokenProvider:
    """SFC token provider configured for simulated login service."""
    return HttpSfcTokenProvider(
        login_url=LOGIN_URL,
        border_post_id=42,
        box_id=7,
        passenger_control_type=1,
        timeout=5,
    )


@pytest.fixture()
def downloader() -> HttpBinaryDownloader:
    """Binary downloader configured for simulated certificate service."""
    return HttpBinaryDownloader(
        download_url=DOWNLOAD_URL,
        timeout=5,
    )


# ═══════════════════════════════════════════════════════════════════════
# Full 3-Endpoint Flow — Happy Path
# ═══════════════════════════════════════════════════════════════════════


class TestFullHttpFlowSuccess:
    """
    Integration test simulating all 3 REST endpoints responding successfully.

    GIVEN simulated Keycloak, SFC login, and download services
    WHEN the adapters are called in sequence (access_token → sfc_token → download)
    THEN all three calls succeed and the binary content is returned.
    """

    @respx.mock
    def test_full_flow_returns_binary_content(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN Keycloak returns access_token, SFC returns sfc_token, download returns .bin
        WHEN the 3-step flow is executed
        THEN the final result contains the binary content.
        """
        # Step 1: Keycloak responds with access_token
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "access-token-abc"})
        )
        # Step 2: SFC login responds with sfc_token
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, text="sfc-token-xyz")
        )
        # Step 3: Download returns binary content
        expected_bin = b"\x30\x82\x01\x00" + b"\xCA\xFE" * 100
        respx.get(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=expected_bin)
        )

        # Execute the flow
        access_result = access_provider.acquire_token()
        access_token = ResultAssertions.assert_success(access_result)
        assert access_token == "access-token-abc"

        sfc_result = sfc_provider.acquire_token(access_token)
        sfc_token = ResultAssertions.assert_success(sfc_result)
        assert sfc_token == "sfc-token-xyz"

        credentials = AuthCredentials(access_token=access_token, sfc_token=sfc_token)
        download_result = downloader.download(credentials)
        data = ResultAssertions.assert_success(download_result)
        assert data == expected_bin

    @respx.mock
    def test_full_flow_sends_correct_headers_at_each_step(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN simulated services
        WHEN the 3-step flow is executed
        THEN Step 1 sends password grant form data
        AND Step 2 sends Bearer header + JSON body
        AND Step 3 sends dual-token headers.
        """
        auth_route = respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "at-123"})
        )
        login_route = respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, text="sfc-456")
        )
        download_route = respx.get(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"bin-data")
        )

        # Execute flow
        access_token = ResultAssertions.assert_success(access_provider.acquire_token())
        sfc_token = ResultAssertions.assert_success(sfc_provider.acquire_token(access_token))
        credentials = AuthCredentials(access_token=access_token, sfc_token=sfc_token)
        ResultAssertions.assert_success(downloader.download(credentials))

        # Verify Step 1: password grant form data
        auth_request = auth_route.calls.last.request
        auth_body = auth_request.content.decode()
        assert "grant_type=password" in auth_body
        assert "cert-parser-client" in auth_body
        assert "super-secret-123" in auth_body
        assert "operator%40border.gov" in auth_body or "operator@border.gov" in auth_body
        assert "operator-pass" in auth_body

        # Verify Step 2: Bearer header + JSON body
        login_request = login_route.calls.last.request
        assert login_request.headers["authorization"] == "Bearer at-123"
        import json

        login_body = json.loads(login_request.content)
        assert login_body == {"borderPostId": 42, "boxId": 7, "passengerControlType": 1}

        # Verify Step 3: dual-token headers
        download_request = download_route.calls.last.request
        assert download_request.headers["authorization"] == "Bearer at-123"
        assert download_request.headers["x-sfc-authorization"] == "Bearer sfc-456"


# ═══════════════════════════════════════════════════════════════════════
# Failure Cascade — Step 1 Fails
# ═══════════════════════════════════════════════════════════════════════


class TestFlowStep1Failure:
    """
    GIVEN Keycloak is down or rejects credentials
    WHEN Step 1 fails
    THEN the flow stops — Steps 2 and 3 are never attempted.
    """

    @respx.mock
    def test_keycloak_401_stops_flow(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN Keycloak responds 401 (bad credentials)
        WHEN acquire_access_token is called
        THEN it returns Failure(AUTHENTICATION_ERROR)
        AND no SFC login or download is attempted.
        """
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_grant"})
        )
        login_route = respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, text="should-not-reach")
        )
        download_route = respx.get(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"should-not-reach")
        )

        result = access_provider.acquire_token()

        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)
        assert not login_route.called
        assert not download_route.called

    @respx.mock
    def test_keycloak_timeout_stops_flow(
        self,
        access_provider: HttpAccessTokenProvider,
    ) -> None:
        """
        GIVEN Keycloak times out
        WHEN acquire_access_token is called
        THEN it returns Failure (does not raise).
        """
        respx.post(AUTH_URL).mock(side_effect=httpx.ConnectTimeout("Keycloak unreachable"))

        result = access_provider.acquire_token()

        assert result.is_failure()


# ═══════════════════════════════════════════════════════════════════════
# Failure Cascade — Step 2 Fails
# ═══════════════════════════════════════════════════════════════════════


class TestFlowStep2Failure:
    """
    GIVEN Keycloak succeeded but SFC login fails
    WHEN Step 2 fails
    THEN the flow stops — Step 3 is never attempted.
    """

    @respx.mock
    def test_sfc_login_401_after_valid_access_token(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN Keycloak returns a valid access_token
        AND SFC login responds 401
        WHEN the flow is executed
        THEN Step 1 succeeds, Step 2 fails with AUTHENTICATION_ERROR.
        """
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "valid-at"})
        )
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        download_route = respx.get(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"should-not-reach")
        )

        access_token = ResultAssertions.assert_success(access_provider.acquire_token())
        sfc_result = sfc_provider.acquire_token(access_token)

        ResultAssertions.assert_failure(sfc_result, ErrorCode.AUTHENTICATION_ERROR)
        assert not download_route.called


# ═══════════════════════════════════════════════════════════════════════
# Failure Cascade — Step 3 Fails
# ═══════════════════════════════════════════════════════════════════════


class TestFlowStep3Failure:
    """
    GIVEN Steps 1 and 2 succeeded but download fails
    WHEN Step 3 fails
    THEN download returns Failure(EXTERNAL_SERVICE_ERROR).
    """

    @respx.mock
    def test_download_500_after_valid_tokens(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN valid access_token and sfc_token obtained
        AND download server responds 500
        WHEN download is called
        THEN it returns Failure(EXTERNAL_SERVICE_ERROR).
        """
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, text="sfc")
        )
        respx.get(DOWNLOAD_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        access_token = ResultAssertions.assert_success(access_provider.acquire_token())
        sfc_token = ResultAssertions.assert_success(sfc_provider.acquire_token(access_token))
        credentials = AuthCredentials(access_token=access_token, sfc_token=sfc_token)
        result = downloader.download(credentials)

        ResultAssertions.assert_failure(result, ErrorCode.EXTERNAL_SERVICE_ERROR)

    @respx.mock
    def test_download_network_error_after_valid_tokens(
        self,
        access_provider: HttpAccessTokenProvider,
        sfc_provider: HttpSfcTokenProvider,
        downloader: HttpBinaryDownloader,
    ) -> None:
        """
        GIVEN valid tokens obtained
        AND download server connection fails
        WHEN download is called
        THEN it returns Failure (does not raise).
        """
        respx.post(AUTH_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, text="sfc")
        )
        respx.get(DOWNLOAD_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        access_token = ResultAssertions.assert_success(access_provider.acquire_token())
        sfc_token = ResultAssertions.assert_success(sfc_provider.acquire_token(access_token))
        credentials = AuthCredentials(access_token=access_token, sfc_token=sfc_token)
        result = downloader.download(credentials)

        assert result.is_failure()
