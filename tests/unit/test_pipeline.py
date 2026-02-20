"""
Unit tests for the ROP pipeline — orchestrates the full workflow.

TDD RED phase — these tests are written BEFORE the implementation.
Uses mock ports (fake adapters) to test the pipeline in isolation.

The pipeline now has 5 stages (dual-token authentication):
  1. acquire_access_token() → access_token
  2. acquire_sfc_token(access_token) → sfc_token → AuthCredentials
  3. download(credentials) → binary
  4. parse(binary) → payload
  5. store(payload) → row_count

Test categories:
  - Success track: all ports succeed → pipeline returns Result.success(rows)
  - Failure at each stage: access_token/sfc_token/download/parse/store fails
  - Short-circuit: early failure prevents later stages from being called
"""

from __future__ import annotations

from unittest.mock import MagicMock

from railway import ErrorCode, Result, ResultAssertions

from cert_parser.domain.models import AuthCredentials, CertificateRecord, MasterListPayload
from cert_parser.pipeline import run_pipeline

# ─────────────────────── Mock Port Factories ───────────────────────


def _make_access_token_provider(result: Result[str]) -> MagicMock:
    """Create a mock AccessTokenProvider returning the given Result."""
    mock = MagicMock()
    mock.acquire_token.return_value = result
    return mock


def _make_sfc_token_provider(result: Result[str]) -> MagicMock:
    """Create a mock SfcTokenProvider returning the given Result."""
    mock = MagicMock()
    mock.acquire_token.return_value = result
    return mock


def _make_downloader(result: Result[bytes]) -> MagicMock:
    """Create a mock BinaryDownloader returning the given Result."""
    mock = MagicMock()
    mock.download.return_value = result
    return mock


def _make_parser(result: Result[MasterListPayload]) -> MagicMock:
    """Create a mock MasterListParser returning the given Result."""
    mock = MagicMock()
    mock.parse.return_value = result
    return mock


def _make_repository(result: Result[int]) -> MagicMock:
    """Create a mock CertificateRepository returning the given Result."""
    mock = MagicMock()
    mock.store.return_value = result
    return mock


def _sample_payload() -> MasterListPayload:
    """Create a minimal valid MasterListPayload for testing."""
    return MasterListPayload(
        root_cas=[
            CertificateRecord(certificate=b"\x30\x82\x01\x00", source="test"),
        ],
    )


# ─────────────────────── Success Track ───────────────────────


class TestPipelineSuccess:
    """
    GIVEN all five ports return success values
    WHEN run_pipeline is called
    THEN it returns Result.success with the row count from the repository.
    """

    def test_returns_success_with_row_count(self) -> None:
        """
        GIVEN access_token="abc", sfc_token="sfc-xyz", download=binary, parse=payload, store=42
        WHEN run_pipeline is called
        THEN it returns Success(42).
        """
        access_tp = _make_access_token_provider(Result.success("abc-token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc-xyz"))
        downloader = _make_downloader(Result.success(b"\x30\x82"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(42))

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        rows = ResultAssertions.assert_success(result)
        assert rows == 42

    def test_calls_all_ports_in_order(self) -> None:
        """
        GIVEN all ports succeed
        WHEN run_pipeline is called
        THEN all five ports are called exactly once.
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc-token"))
        downloader = _make_downloader(Result.success(b"data"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(10))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        access_tp.acquire_token.assert_called_once()
        sfc_tp.acquire_token.assert_called_once_with("token")
        downloader.download.assert_called_once()
        parser.parse.assert_called_once_with(b"data")
        repository.store.assert_called_once()

    def test_passes_access_token_to_sfc_provider(self) -> None:
        """
        GIVEN access_token_provider returns "my-access-token"
        WHEN run_pipeline is called
        THEN sfc_token_provider.acquire_token receives "my-access-token".
        """
        access_tp = _make_access_token_provider(Result.success("my-access-token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"binary"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(5))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        sfc_tp.acquire_token.assert_called_once_with("my-access-token")

    def test_passes_auth_credentials_to_downloader(self) -> None:
        """
        GIVEN access_token="at" and sfc_token="sfc"
        WHEN run_pipeline is called
        THEN downloader.download receives AuthCredentials(access_token="at", sfc_token="sfc").
        """
        access_tp = _make_access_token_provider(Result.success("at"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"binary"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(1))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        expected_creds = AuthCredentials(access_token="at", sfc_token="sfc")
        downloader.download.assert_called_once_with(expected_creds)

    def test_passes_payload_to_repository(self) -> None:
        """
        GIVEN parser returns a MasterListPayload
        WHEN run_pipeline is called
        THEN repository.store receives that exact payload.
        """
        payload = _sample_payload()
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"data"))
        parser = _make_parser(Result.success(payload))
        repository = _make_repository(Result.success(1))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        repository.store.assert_called_once_with(payload)


# ─────────────────────── Failure at Each Stage ───────────────────────


class TestPipelineAccessTokenFailure:
    """
    GIVEN access token acquisition fails
    WHEN run_pipeline is called
    THEN it returns Result.failure(AUTHENTICATION_ERROR).
    """

    def test_returns_authentication_error(self) -> None:
        """
        GIVEN access_token_provider returns Failure(AUTHENTICATION_ERROR)
        WHEN run_pipeline is called
        THEN pipeline returns Failure(AUTHENTICATION_ERROR).
        """
        access_tp = _make_access_token_provider(
            Result.failure(ErrorCode.AUTHENTICATION_ERROR, "invalid credentials")
        )
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b""))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestPipelineSfcTokenFailure:
    """
    GIVEN SFC login fails
    WHEN run_pipeline is called
    THEN it returns Result.failure(AUTHENTICATION_ERROR).
    """

    def test_returns_authentication_error(self) -> None:
        """
        GIVEN sfc_token_provider returns Failure(AUTHENTICATION_ERROR)
        WHEN run_pipeline is called
        THEN pipeline returns Failure(AUTHENTICATION_ERROR).
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(
            Result.failure(ErrorCode.AUTHENTICATION_ERROR, "SFC login failed")
        )
        downloader = _make_downloader(Result.success(b""))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)


class TestPipelineDownloadFailure:
    """
    GIVEN download fails
    WHEN run_pipeline is called
    THEN it returns Result.failure(EXTERNAL_SERVICE_ERROR).
    """

    def test_returns_external_service_error(self) -> None:
        """
        GIVEN downloader returns Failure(EXTERNAL_SERVICE_ERROR)
        WHEN run_pipeline is called
        THEN pipeline returns Failure(EXTERNAL_SERVICE_ERROR).
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.failure(ErrorCode.EXTERNAL_SERVICE_ERROR, "HTTP 500"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        ResultAssertions.assert_failure(result, ErrorCode.EXTERNAL_SERVICE_ERROR)


class TestPipelineParseFailure:
    """
    GIVEN parsing fails
    WHEN run_pipeline is called
    THEN it returns Result.failure(TECHNICAL_ERROR).
    """

    def test_returns_technical_error(self) -> None:
        """
        GIVEN parser returns Failure(TECHNICAL_ERROR)
        WHEN run_pipeline is called
        THEN pipeline returns Failure(TECHNICAL_ERROR).
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"corrupt"))
        parser = _make_parser(Result.failure(ErrorCode.TECHNICAL_ERROR, "Invalid CMS"))
        repository = _make_repository(Result.success(0))

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)


class TestPipelineStoreFailure:
    """
    GIVEN database store fails
    WHEN run_pipeline is called
    THEN it returns Result.failure(DATABASE_ERROR).
    """

    def test_returns_database_error(self) -> None:
        """
        GIVEN repository returns Failure(DATABASE_ERROR)
        WHEN run_pipeline is called
        THEN pipeline returns Failure(DATABASE_ERROR).
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"data"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(
            Result.failure(ErrorCode.DATABASE_ERROR, "connection refused")
        )

        result = run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        ResultAssertions.assert_failure(result, ErrorCode.DATABASE_ERROR)


# ─────────────────────── Short-Circuit Behavior ───────────────────────


class TestPipelineShortCircuit:
    """
    GIVEN an early stage fails
    WHEN run_pipeline is called
    THEN subsequent stages are NOT called.
    """

    def test_access_token_failure_skips_all_subsequent(self) -> None:
        """
        GIVEN access_token_provider fails
        WHEN run_pipeline is called
        THEN sfc_token, download, parse, and store are never called.
        """
        access_tp = _make_access_token_provider(
            Result.failure(ErrorCode.AUTHENTICATION_ERROR, "bad creds")
        )
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b""))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        sfc_tp.acquire_token.assert_not_called()
        downloader.download.assert_not_called()
        parser.parse.assert_not_called()
        repository.store.assert_not_called()

    def test_sfc_token_failure_skips_download_parse_store(self) -> None:
        """
        GIVEN sfc_token_provider fails
        WHEN run_pipeline is called
        THEN download, parse, and store are never called.
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(
            Result.failure(ErrorCode.AUTHENTICATION_ERROR, "SFC login failed")
        )
        downloader = _make_downloader(Result.success(b""))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        downloader.download.assert_not_called()
        parser.parse.assert_not_called()
        repository.store.assert_not_called()

    def test_download_failure_skips_parse_store(self) -> None:
        """
        GIVEN downloader fails
        WHEN run_pipeline is called
        THEN parse and store are never called.
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.failure(ErrorCode.EXTERNAL_SERVICE_ERROR, "503"))
        parser = _make_parser(Result.success(_sample_payload()))
        repository = _make_repository(Result.success(0))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        parser.parse.assert_not_called()
        repository.store.assert_not_called()

    def test_parse_failure_skips_store(self) -> None:
        """
        GIVEN parser fails
        WHEN run_pipeline is called
        THEN store is never called.
        """
        access_tp = _make_access_token_provider(Result.success("token"))
        sfc_tp = _make_sfc_token_provider(Result.success("sfc"))
        downloader = _make_downloader(Result.success(b"data"))
        parser = _make_parser(Result.failure(ErrorCode.TECHNICAL_ERROR, "corrupt CMS"))
        repository = _make_repository(Result.success(0))

        run_pipeline(access_tp, sfc_tp, downloader, parser, repository)

        repository.store.assert_not_called()
