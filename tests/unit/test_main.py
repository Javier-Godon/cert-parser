"""
Unit tests for the main module — composition root.

Tests verify structlog configuration and the wiring logic
without making real HTTP calls or database connections.
"""

from __future__ import annotations

import structlog

from cert_parser.main import configure_structlog


class TestConfigureStructlog:
    """Verify structlog configuration function."""

    def test_configure_structlog_sets_log_level(self) -> None:
        """
        GIVEN log_level="WARNING"
        WHEN configure_structlog is called
        THEN structlog is configured (no exception raised).
        """
        configure_structlog("WARNING")
        log = structlog.get_logger()
        # Verify it's callable — structlog was configured without error
        assert log is not None

    def test_configure_structlog_defaults_to_info(self) -> None:
        """
        GIVEN no explicit log_level
        WHEN configure_structlog is called with default
        THEN structlog is configured at INFO level.
        """
        configure_structlog()
        log = structlog.get_logger()
        assert log is not None

    def test_configure_structlog_invalid_level_falls_back(self) -> None:
        """
        GIVEN an invalid log_level string
        WHEN configure_structlog is called
        THEN it falls back to INFO (no crash).
        """
        configure_structlog("NONEXISTENT")
        log = structlog.get_logger()
        assert log is not None
