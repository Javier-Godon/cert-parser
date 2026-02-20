"""
Acceptance test fixtures — PostgreSQL testcontainer for end-to-end tests.

Reuses the same DDL and pattern as integration tests but scoped for acceptance.
"""

from __future__ import annotations

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from tests.integration.conftest import DDL, TRUNCATE_ALL


@pytest.fixture(scope="session")
def acceptance_pg() -> PostgresContainer:
    """Start a PostgreSQL container for the acceptance test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            conn.commit()
        yield pg


@pytest.fixture()
def acceptance_dsn(acceptance_pg: PostgresContainer) -> str:
    """Return a psycopg-compatible DSN and truncate all tables before each test."""
    connection_url = acceptance_pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
    with psycopg.connect(connection_url) as conn:
        conn.execute(TRUNCATE_ALL)
        conn.commit()
    return connection_url
