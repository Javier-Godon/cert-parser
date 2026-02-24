"""
Integration test fixtures — PostgreSQL testcontainer and schema setup.

Provides a real PostgreSQL instance for each test session via testcontainers.
Creates all four tables matching the production schema.
Each test gets a fresh, clean database via truncation.
"""

from __future__ import annotations

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

DDL = """
CREATE TABLE root_ca (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    master_list_issuer        TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE dsc (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE crls (
    id          UUID PRIMARY KEY,
    crl         BYTEA NOT NULL,
    source      TEXT,
    issuer      TEXT,
    country     TEXT,
    updated_at  TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE revoked_certificate_list (
    id                UUID PRIMARY KEY,
    source            TEXT,
    country           TEXT,
    isn               TEXT,
    crl               UUID REFERENCES crls(id),
    revocation_reason TEXT,
    revocation_date   TIMESTAMP WITHOUT TIME ZONE,
    updated_at        TIMESTAMP WITHOUT TIME ZONE
);
"""

TRUNCATE_ALL = """
TRUNCATE revoked_certificate_list, crls, dsc, root_ca CASCADE;
"""


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Start a PostgreSQL container for the entire test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            conn.commit()
        yield pg


@pytest.fixture()
def dsn(postgres_container: PostgresContainer) -> str:
    """Return a psycopg-compatible DSN and truncate all tables before each test."""
    connection_url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql"
    )
    with psycopg.connect(connection_url) as conn:
        conn.execute(TRUNCATE_ALL)
        conn.commit()
    return connection_url
