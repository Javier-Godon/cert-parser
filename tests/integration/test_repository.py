"""
Integration tests for PsycopgCertificateRepository.

Tests run against a real PostgreSQL instance via testcontainers.
Each test verifies the transactional replace pattern:
  DELETE all → INSERT new → COMMIT (or ROLLBACK on failure).

BDD-style docstrings describe the specification.

Markers: @pytest.mark.integration — requires Docker + PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from railway import ErrorCode
from railway.assertions import ResultAssertions

from cert_parser.adapters.repository import PsycopgCertificateRepository
from cert_parser.domain.models import (
    CertificateRecord,
    CrlRecord,
    MasterListPayload,
    RevokedCertificateRecord,
)

pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_cert(
    source: str = "csca",
    issuer: str = "CN=Test CA,C=XX",
    ski: str | None = "aa:bb:cc",
) -> CertificateRecord:
    """Create a minimal CertificateRecord for testing."""
    return CertificateRecord(
        certificate=b"\x30\x82\x00\x01" + b"\x00" * 100,
        id=uuid4(),
        subject_key_identifier=ski,
        authority_key_identifier="dd:ee:ff",
        issuer=issuer,
        x_500_issuer=b"\x30\x0b",
        source=source,
        isn="test-isn",
        updated_at=datetime(2025, 1, 1, 12, 0, 0),
    )


def _make_crl(
    issuer: str = "CN=Test CA,C=XX",
    country: str = "XX",
) -> CrlRecord:
    """Create a minimal CrlRecord for testing."""
    return CrlRecord(
        crl=b"\x30\x82\x00\x02" + b"\x00" * 50,
        id=uuid4(),
        source="test-source",
        issuer=issuer,
        country=country,
        updated_at=datetime(2025, 1, 1, 12, 0, 0),
    )


def _make_revoked(crl_id: UUID | None = None) -> RevokedCertificateRecord:
    """Create a minimal RevokedCertificateRecord for testing."""
    return RevokedCertificateRecord(
        id=uuid4(),
        source="test-source",
        country="XX",
        isn="test-isn",
        crl=crl_id,
        revocation_reason="keyCompromise",
        revocation_date=datetime(2024, 6, 15, 10, 0, 0),
        updated_at=datetime(2025, 1, 1, 12, 0, 0),
    )


def _count_rows(dsn: str, table: str) -> int:
    """Count rows in a given table."""
    with psycopg.connect(dsn) as conn:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        return row[0] if row else 0


# ── Test: Happy Path — Store Single Payload ──────────────────────────────────


class TestStoreHappyPath:
    """Verify successful storage of a complete payload."""

    def test_store_root_cas(self, dsn: str) -> None:
        """
        GIVEN a payload with 2 root CA certificates
        WHEN the repository stores the payload
        THEN both certificates are persisted to the root_ca table
        AND the result is a Success with total row count.
        """
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(
            root_cas=[_make_cert("csca"), _make_cert("csca", issuer="CN=Other,C=YY")],
        )

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 2
        assert _count_rows(dsn, "root_ca") == 2

    def test_store_dscs(self, dsn: str) -> None:
        """
        GIVEN a payload with 1 DSC certificate
        WHEN the repository stores the payload
        THEN the certificate is persisted to the dsc table.
        """
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(dscs=[_make_cert("dsc")])

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 1
        assert _count_rows(dsn, "dsc") == 1

    def test_store_crls(self, dsn: str) -> None:
        """
        GIVEN a payload with 1 CRL
        WHEN the repository stores the payload
        THEN the CRL is persisted to the crls table.
        """
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(crls=[_make_crl()])

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 1
        assert _count_rows(dsn, "crls") == 1

    def test_store_revoked_with_crl_fk(self, dsn: str) -> None:
        """
        GIVEN a payload with 1 CRL and 1 revoked certificate referencing it
        WHEN the repository stores the payload
        THEN both are persisted and the FK constraint is satisfied.
        """
        crl = _make_crl()
        revoked = _make_revoked(crl_id=crl.id)
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(crls=[crl], revoked_certificates=[revoked])

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 2
        assert _count_rows(dsn, "crls") == 1
        assert _count_rows(dsn, "revoked_certificate_list") == 1

    def test_store_full_payload(self, dsn: str) -> None:
        """
        GIVEN a payload with root CAs, DSCs, CRLs, and revoked certificates
        WHEN the repository stores the payload
        THEN all rows are persisted across all four tables
        AND the total row count matches.
        """
        crl = _make_crl()
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(
            root_cas=[_make_cert("csca"), _make_cert("csca")],
            dscs=[_make_cert("dsc")],
            crls=[crl],
            revoked_certificates=[_make_revoked(crl_id=crl.id)],
        )

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 5
        assert _count_rows(dsn, "root_ca") == 2
        assert _count_rows(dsn, "dsc") == 1
        assert _count_rows(dsn, "crls") == 1
        assert _count_rows(dsn, "revoked_certificate_list") == 1


# ── Test: Empty Payload ──────────────────────────────────────────────────────


class TestStoreEmptyPayload:
    """Verify correct handling of an empty payload."""

    def test_store_empty_payload_succeeds(self, dsn: str) -> None:
        """
        GIVEN an empty payload (no certs, no CRLs, no revoked)
        WHEN the repository stores it
        THEN the result is Success(0) and all tables are empty.
        """
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload()

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 0
        assert _count_rows(dsn, "root_ca") == 0


# ── Test: Transactional Replace ──────────────────────────────────────────────


class TestTransactionalReplace:
    """Verify the DELETE + INSERT atomicity contract."""

    def test_second_store_replaces_first(self, dsn: str) -> None:
        """
        GIVEN the repository contains data from a first store
        WHEN a second store is called with different data
        THEN the old data is deleted and only the new data remains.
        """
        repo = PsycopgCertificateRepository(dsn)
        first = MasterListPayload(
            root_cas=[_make_cert("csca", issuer="CN=Old,C=XX")],
        )
        second = MasterListPayload(
            root_cas=[
                _make_cert("csca", issuer="CN=New1,C=YY"),
                _make_cert("csca", issuer="CN=New2,C=ZZ"),
            ],
        )

        repo.store(first)
        result = repo.store(second)

        count = ResultAssertions.assert_success(result)
        assert count == 2
        assert _count_rows(dsn, "root_ca") == 2

        # Verify old data is gone
        with psycopg.connect(dsn) as conn:
            rows = conn.execute("SELECT issuer FROM root_ca ORDER BY issuer").fetchall()
            issuers = [r[0] for r in rows]
            assert "CN=Old,C=XX" not in issuers
            assert "CN=New1,C=YY" in issuers
            assert "CN=New2,C=ZZ" in issuers

    def test_empty_store_clears_previous_data(self, dsn: str) -> None:
        """
        GIVEN the repository contains data from a previous store
        WHEN an empty payload is stored
        THEN all previous data is removed.
        """
        repo = PsycopgCertificateRepository(dsn)
        first = MasterListPayload(root_cas=[_make_cert()])
        repo.store(first)
        assert _count_rows(dsn, "root_ca") == 1

        result = repo.store(MasterListPayload())

        ResultAssertions.assert_success(result)
        assert _count_rows(dsn, "root_ca") == 0


# ── Test: NULL Fields ────────────────────────────────────────────────────────


class TestNullHandling:
    """Verify correct handling of optional/NULL fields."""

    def test_store_cert_with_null_optional_fields(self, dsn: str) -> None:
        """
        GIVEN a certificate record where all optional fields are None
        WHEN the repository stores it
        THEN the row is persisted with NULL values in optional columns.
        """
        cert = CertificateRecord(certificate=b"\x30\x82\x00\x01")
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(root_cas=[cert])

        result = repo.store(payload)

        count = ResultAssertions.assert_success(result)
        assert count == 1
        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT subject_key_identifier, issuer, source FROM root_ca"
            ).fetchone()
            assert row is not None
            assert row[0] is None  # ski
            assert row[1] is None  # issuer
            assert row[2] is None  # source


# ── Test: Data Integrity ─────────────────────────────────────────────────────


class TestDataIntegrity:
    """Verify that stored data matches input exactly."""

    def test_certificate_bytes_round_trip(self, dsn: str) -> None:
        """
        GIVEN a certificate with specific DER bytes
        WHEN stored and then read back
        THEN the bytes are identical (no corruption).
        """
        der_bytes = b"\x30\x82\x01\x00" + bytes(range(256))
        cert = CertificateRecord(
            certificate=der_bytes,
            id=uuid4(),
            subject_key_identifier="aa:bb:cc:dd",
            issuer="CN=RoundTrip,C=RT",
        )
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(root_cas=[cert])
        repo.store(payload)

        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT certificate, subject_key_identifier, issuer FROM root_ca WHERE id = %s",
                (cert.id,),
            ).fetchone()
            assert row is not None
            assert bytes(row[0]) == der_bytes
            assert row[1] == "aa:bb:cc:dd"
            assert row[2] == "CN=RoundTrip,C=RT"

    def test_crl_bytes_round_trip(self, dsn: str) -> None:
        """
        GIVEN a CRL with specific DER bytes
        WHEN stored and then read back
        THEN the bytes are identical.
        """
        crl_bytes = b"\x30\x82\x02\x00" + bytes(range(256))
        crl = CrlRecord(
            crl=crl_bytes,
            id=uuid4(),
            issuer="CN=CRL Issuer,C=XX",
            country="XX",
        )
        repo = PsycopgCertificateRepository(dsn)
        payload = MasterListPayload(crls=[crl])
        repo.store(payload)

        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT crl, issuer, country FROM crls WHERE id = %s",
                (crl.id,),
            ).fetchone()
            assert row is not None
            assert bytes(row[0]) == crl_bytes
            assert row[1] == "CN=CRL Issuer,C=XX"
            assert row[2] == "XX"


# ── Test: Connection Error ───────────────────────────────────────────────────


class TestConnectionError:
    """Verify graceful failure on connection errors."""

    def test_store_with_bad_dsn_returns_failure(self) -> None:
        """
        GIVEN a repository configured with an unreachable DSN
        WHEN store is called
        THEN it returns a Failure with DATABASE_ERROR.
        """
        repo = PsycopgCertificateRepository("postgresql://bad:bad@localhost:1/nope")
        payload = MasterListPayload(root_cas=[_make_cert()])

        result = repo.store(payload)

        ResultAssertions.assert_failure(result, ErrorCode.DATABASE_ERROR)
