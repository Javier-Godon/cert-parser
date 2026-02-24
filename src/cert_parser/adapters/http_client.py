"""
HTTP adapter — dual-token authentication and binary download via httpx.

Adapter layer — implements AccessTokenProvider, SfcTokenProvider, and BinaryDownloader
ports using httpx for sync HTTP calls.

Authentication flow (3 endpoints):
  1. OpenID Connect password grant → access_token
  2. SFC login with access_token + border post config → sfc_token
  3. Download with both tokens (Authorization + x-sfc-authorization)

Retry/backoff via tenacity on transient errors (network, timeout).
All HTTP errors are captured into Result failures — no exceptions
leak to the business logic layer.
"""

from __future__ import annotations

import httpx
import structlog
from railway import ErrorCode
from railway.result import Result
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from cert_parser.domain.models import AuthCredentials

log = structlog.get_logger()


class HttpAccessTokenProvider:
    """
    Acquire OAuth2 access tokens via password grant (OpenID Connect).

    Implements the AccessTokenProvider port.
    Uses tenacity retry on transient network errors only.
    """

    def __init__(
        self,
        auth_url: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        timeout: int = 60,
    ) -> None:
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._timeout = timeout

    def acquire_token(self) -> Result[str]:
        """
        Request an access token from the OpenID Connect endpoint.

        Calls POST {auth_url}/protocol/openid-connect/token with
        grant_type=password and client + user credentials.
        Returns Result[str] with the access_token on success,
        or Result.failure(AUTHENTICATION_ERROR, ...) on failure.
        """
        return Result.from_computation(
            lambda: self._do_token_request(),
            ErrorCode.AUTHENTICATION_ERROR,
            "Access token acquisition failed",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def _do_token_request(self) -> str:
        """HTTP call with retry — exceptions caught by from_computation."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._auth_url,
                data={
                    "grant_type": "password",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "username": self._username,
                    "password": self._password,
                },
            )
            response.raise_for_status()
            token: str = response.json()["access_token"]
            log.info("access_token.acquired")
            return token


class HttpSfcTokenProvider:
    """
    Acquire SFC authentication tokens via the login endpoint.

    Implements the SfcTokenProvider port.
    Uses tenacity retry on transient network errors only.
    """

    def __init__(
        self,
        login_url: str,
        border_post_id: str,
        box_id: str,
        passenger_control_type: str,
        timeout: int = 60,
    ) -> None:
        self._login_url = login_url
        self._border_post_id = border_post_id
        self._box_id = box_id
        self._passenger_control_type = passenger_control_type
        self._timeout = timeout

    def acquire_token(self, access_token: str) -> Result[str]:
        """
        Request an SFC token from the login endpoint.

        Calls POST {login_url}/auth/v1/login with the access_token as Bearer
        and a JSON body containing borderPostId, boxId, passengerControlType.
        Returns Result[str] with the SFC token on success,
        or Result.failure(AUTHENTICATION_ERROR, ...) on failure.
        """
        return Result.from_computation(
            lambda: self._do_login_request(access_token),
            ErrorCode.AUTHENTICATION_ERROR,
            "SFC token acquisition failed",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def _do_login_request(self, access_token: str) -> str:
        """HTTP call with retry — exceptions caught by from_computation."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._login_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "borderPostId": self._border_post_id,
                    "boxId": self._box_id,
                    "passengerControlType": self._passenger_control_type,
                },
            )
            response.raise_for_status()
            token: str = response.text
            log.info("sfc_token.acquired")
            return token


class HttpBinaryDownloader:
    """
    Download Master List .bin files via HTTP GET with dual-token auth.

    Implements the BinaryDownloader port.
    Uses tenacity retry on transient network errors only.
    """

    def __init__(
        self,
        download_url: str,
        timeout: int = 60,
    ) -> None:
        self._download_url = download_url
        self._timeout = timeout

    def download(self, credentials: AuthCredentials) -> Result[bytes]:
        """
        Download the .bin Master List bundle using dual-token authentication.

        Sends GET request with both Authorization (access_token) and
        x-sfc-authorization (sfc_token) headers.
        Returns Result[bytes] with raw binary content on success,
        or Result.failure(EXTERNAL_SERVICE_ERROR, ...) on failure.
        """
        return Result.from_computation(
            lambda: self._do_download(credentials),
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            "Binary download failed",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def _do_download(self, credentials: AuthCredentials) -> bytes:
        """HTTP GET with retry — exceptions caught by from_computation."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(
                self._download_url,
                headers={
                    "Authorization": f"Bearer {credentials.access_token}",
                    "x-sfc-authorization": f"Bearer {credentials.sfc_token}",
                },
            )
            response.raise_for_status()
            data = response.content
            log.info("download.complete", size_bytes=len(data))
            return data
