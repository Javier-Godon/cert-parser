"""
Shared test fixtures and helpers for the cert-parser test suite.

Provides path resolution for ICAO test fixture files (.bin, .der)
extracted from the ICAO PKD LDIF data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixtures_dir() -> Path:
    """Return the absolute path to the test fixtures directory."""
    return FIXTURES_DIR


def fixture_path(filename: str) -> Path:
    """
    Resolve the absolute path to a test fixture file.

    Raises FileNotFoundError if the fixture does not exist.
    """
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Test fixture not found: {path}")
    return path
