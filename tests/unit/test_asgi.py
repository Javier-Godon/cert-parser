"""
Unit tests for the FastAPI ASGI application — REST endpoints.

Tests the /trigger endpoint for manual pipeline execution,
as well as /health, /ready, and /info probes.

Uses FastAPI's TestClient with mocked pipeline and scheduler state.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from railway import ErrorCode, Result

from cert_parser import asgi


@pytest.fixture(autouse=True)
def _reset_asgi_state() -> None:
    """Reset ASGI module-level state before each test."""
    asgi._scheduler_thread = None
    asgi._scheduler_started = False
    asgi._scheduler_ready = False
    asgi._error_message = None
    asgi._pipeline_fn = None


@pytest.fixture()
def client() -> TestClient:
    """Create a TestClient without running the lifespan (no real startup)."""
    return TestClient(asgi.app, raise_server_exceptions=False)


# ─────────────────────── POST /trigger ───────────────────────


class TestTriggerEndpoint:
    """Tests for the POST /trigger endpoint — manual pipeline execution."""

    def test_trigger_returns_503_when_pipeline_not_initialized(
        self, client: TestClient,
    ) -> None:
        """
        GIVEN the application has not completed startup (pipeline_fn is None)
        WHEN POST /trigger is called
        THEN it returns 503 with an unavailable status.
        """
        response = client.post("/trigger")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unavailable"
        assert "not initialized" in body["reason"]

    def test_trigger_returns_200_on_pipeline_success(
        self, client: TestClient,
    ) -> None:
        """
        GIVEN the pipeline is initialized and succeeds with 42 rows stored
        WHEN POST /trigger is called
        THEN it returns 200 with rows_stored=42.
        """
        asgi._pipeline_fn = lambda: Result.success(42)

        response = client.post("/trigger")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["rows_stored"] == 42

    def test_trigger_returns_500_on_pipeline_failure(
        self, client: TestClient,
    ) -> None:
        """
        GIVEN the pipeline is initialized but fails with a database error
        WHEN POST /trigger is called
        THEN it returns 500 with error details.
        """
        asgi._pipeline_fn = lambda: Result.failure(
            ErrorCode.DATABASE_ERROR, "Connection refused",
        )

        response = client.post("/trigger")

        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "failed"
        assert "DATABASE" in body["error_code"]
        assert "Connection refused" in body["message"]

    def test_trigger_returns_500_on_unexpected_exception(
        self, client: TestClient,
    ) -> None:
        """
        GIVEN the pipeline raises an unexpected exception
        WHEN POST /trigger is called
        THEN it returns 500 with the exception message.
        """

        def _exploding_pipeline() -> Result[int]:
            raise RuntimeError("Unexpected kaboom")

        asgi._pipeline_fn = _exploding_pipeline

        response = client.post("/trigger")

        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "error"
        assert "kaboom" in body["error"]


# ─────────────────────── GET /health ───────────────────────


class TestHealthEndpoint:
    """Tests for the GET /health liveness probe."""

    def test_health_returns_503_when_no_scheduler_thread(
        self, client: TestClient,
    ) -> None:
        """
        GIVEN no scheduler thread is running
        WHEN GET /health is called
        THEN it returns 503.
        """
        response = client.get("/health")
        assert response.status_code == 503

    def test_health_returns_503_on_error(self, client: TestClient) -> None:
        """
        GIVEN a startup error occurred
        WHEN GET /health is called
        THEN it returns 503 with the error message.
        """
        asgi._error_message = "Config broken"

        response = client.get("/health")

        assert response.status_code == 503
        assert "Config broken" in response.json()["error"]

    def test_health_returns_200_with_alive_thread(self, client: TestClient) -> None:
        """
        GIVEN a scheduler thread is alive
        WHEN GET /health is called
        THEN it returns 200.
        """
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        asgi._scheduler_thread = mock_thread

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# ─────────────────────── GET /ready ───────────────────────


class TestReadyEndpoint:
    """Tests for the GET /ready readiness probe."""

    def test_ready_returns_202_when_not_started(self, client: TestClient) -> None:
        """
        GIVEN scheduler has not started
        WHEN GET /ready is called
        THEN it returns 202 (starting).
        """
        response = client.get("/ready")
        assert response.status_code == 202

    def test_ready_returns_200_when_started(self, client: TestClient) -> None:
        """
        GIVEN the scheduler is started and ready
        WHEN GET /ready is called
        THEN it returns 200.
        """
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        asgi._scheduler_thread = mock_thread
        asgi._scheduler_started = True
        asgi._scheduler_ready = True

        response = client.get("/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"


# ─────────────────────── GET /info ───────────────────────


class TestInfoEndpoint:
    """Tests for the GET /info metadata endpoint."""

    def test_info_returns_metadata(self, client: TestClient) -> None:
        """
        GIVEN the application is running
        WHEN GET /info is called
        THEN it returns application metadata.
        """
        response = client.get("/info")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "cert-parser"
        assert body["version"] == "0.1.0"
        assert "scheduler_running" in body
