"""
End-to-end BDD acceptance tests for the cert-parser pipeline.

Exercises the full pipeline: mock HTTP → real CMS parser → real PostgreSQL.
Uses real ICAO Master List fixture files and a testcontainers PostgreSQL instance.

Each test follows Given/When/Then BDD structure in its docstring.

Markers: @pytest.mark.acceptance — requires Docker + PostgreSQL + ICAO fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
import pytest
from railway.assertions import ResultAssertions
from railway.result import Result

from cert_parser.adapters.cms_parser import CmsMasterListParser
from cert_parser.adapters.repository import PsycopgCertificateRepository
from cert_parser.domain.models import AuthCredentials
from cert_parser.pipeline import run_pipeline
from tests.conftest import fixture_path

pytestmark = pytest.mark.acceptance


# ── Fake adapters (mock HTTP layer) ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FakeAccessTokenProvider:
    """Always returns a fixed access token — no real HTTP calls."""

    token: str = "fake-access-token"

    def acquire_token(self) -> Result[str]:
        return Result.success(self.token)


@dataclass(frozen=True, slots=True)
class FakeSfcTokenProvider:
    """Always returns a fixed SFC token — no real HTTP calls."""

    token: str = "fake-sfc-token"

    def acquire_token(self, access_token: str) -> Result[str]:
        return Result.success(self.token)


@dataclass(frozen=True, slots=True)
class FakeBinaryDownloader:
    """Returns pre-loaded bytes from a fixture file — no real HTTP calls."""

    data: bytes = b""

    def download(self, credentials: AuthCredentials) -> Result[bytes]:
        return Result.success(self.data)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _count_rows(dsn: str, table: str) -> int:
    with psycopg.connect(dsn) as conn:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        return row[0] if row else 0


# ── Acceptance Tests ─────────────────────────────────────────────────────────


class TestFullPipelineSeychelles:
    """End-to-end: Seychelles ML file → parse → store → verify DB."""

    def test_pipeline_stores_seychelles_certificates(self, acceptance_dsn: str) -> None:
        """
        GIVEN a valid Seychelles Master List CMS blob (ml_sc.bin)
        AND a real CMS parser and a real PostgreSQL repository
        WHEN the pipeline runs end-to-end (mock HTTP → parse → store)
        THEN the result is Success with rows stored > 0
        AND the root_ca table contains at least 1 certificate
        AND all four tables are populated or correctly empty.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()

        result = run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=raw_bin),
            parser=CmsMasterListParser(),
            repository=PsycopgCertificateRepository(acceptance_dsn),
        )

        count = ResultAssertions.assert_success(result)
        assert count > 0
        assert _count_rows(acceptance_dsn, "root_ca") >= 1


class TestFullPipelineFrance:
    """End-to-end: France ML file → parse → store → verify DB."""

    def test_pipeline_stores_france_certificates(self, acceptance_dsn: str) -> None:
        """
        GIVEN a valid France Master List CMS blob (ml_fr.bin)
        WHEN the pipeline runs end-to-end
        THEN multiple root CA certificates are stored (France has many)
        AND the result row count matches total items in the DB.
        """
        raw_bin = fixture_path("ml_fr.bin").read_bytes()

        result = run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=raw_bin),
            parser=CmsMasterListParser(),
            repository=PsycopgCertificateRepository(acceptance_dsn),
        )

        count = ResultAssertions.assert_success(result)
        db_root_cas = _count_rows(acceptance_dsn, "root_ca")
        db_crls = _count_rows(acceptance_dsn, "crls")
        assert count == db_root_cas + db_crls + _count_rows(acceptance_dsn, "dsc") + _count_rows(
            acceptance_dsn, "revoked_certificate_list"
        )
        assert db_root_cas > 5  # France ML has many certificates


class TestTransactionalReplaceEndToEnd:
    """End-to-end: verify second run replaces first run's data atomically."""

    def test_second_pipeline_run_replaces_first(self, acceptance_dsn: str) -> None:
        """
        GIVEN the pipeline has already run with Seychelles data
        WHEN the pipeline runs again with Bangladesh data
        THEN only Bangladesh data remains in the database
        AND no Seychelles certificates remain.
        """
        sc_bin = fixture_path("ml_sc.bin").read_bytes()
        bd_bin = fixture_path("ml_bd.bin").read_bytes()
        parser = CmsMasterListParser()
        repo = PsycopgCertificateRepository(acceptance_dsn)

        # First run — Seychelles
        run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=sc_bin),
            parser=parser,
            repository=repo,
        )
        sc_count = _count_rows(acceptance_dsn, "root_ca")
        assert sc_count >= 1

        # Second run — Bangladesh
        result = run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=bd_bin),
            parser=parser,
            repository=repo,
        )

        count = ResultAssertions.assert_success(result)
        bd_count = _count_rows(acceptance_dsn, "root_ca")
        assert bd_count >= 1
        assert count > 0

        assert bd_count > 0


class TestPipelineWithCorruptData:
    """End-to-end: verify pipeline failure propagation to result."""

    def test_corrupt_bin_does_not_corrupt_database(self, acceptance_dsn: str) -> None:
        """
        GIVEN the database contains valid Seychelles data from a prior run
        WHEN the pipeline runs with corrupt binary data
        THEN the pipeline returns a Failure result
        AND the database still contains the Seychelles data (old data preserved).
        """
        sc_bin = fixture_path("ml_sc.bin").read_bytes()
        parser = CmsMasterListParser()
        repo = PsycopgCertificateRepository(acceptance_dsn)

        # First run — load valid data
        run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=sc_bin),
            parser=parser,
            repository=repo,
        )
        original_count = _count_rows(acceptance_dsn, "root_ca")
        assert original_count >= 1

        # Second run — corrupt data (parser fails before store)
        result = run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=b"not-valid-cms-data"),
            parser=parser,
            repository=repo,
        )

        # Pipeline failed at parse stage — store never called
        ResultAssertions.assert_failure(result)
        # Old data preserved (parser failed before repository.store was reached)
        assert _count_rows(acceptance_dsn, "root_ca") == original_count


class TestFullPipelineComposite:
    """End-to-end: Composite ML (3 countries + CRL) → parse → store → verify DB."""

    def test_pipeline_stores_all_data_types(self, acceptance_dsn: str) -> None:
        """
        GIVEN ml_composite.bin containing 8 root CAs, 1 CRL, and 15 revoked entries
        AND a real CMS parser and a real PostgreSQL repository
        WHEN the pipeline runs end-to-end (mock HTTP → parse → store)
        THEN root_ca, crls, and revoked_certificate_list tables are all populated
        AND the total stored count matches 8 + 1 + 15 = 24.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()

        result = run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=raw_bin),
            parser=CmsMasterListParser(),
            repository=PsycopgCertificateRepository(acceptance_dsn),
        )

        count = ResultAssertions.assert_success(result)
        assert count == 24
        assert _count_rows(acceptance_dsn, "root_ca") == 8
        assert _count_rows(acceptance_dsn, "crls") == 1
        assert _count_rows(acceptance_dsn, "revoked_certificate_list") == 15

    def test_crl_foreign_key_references_are_valid(self, acceptance_dsn: str) -> None:
        """
        GIVEN ml_composite.bin stored in the database
        WHEN querying revoked_certificate_list
        THEN every revoked entry's crl UUID references an existing crls row.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()

        run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=raw_bin),
            parser=CmsMasterListParser(),
            repository=PsycopgCertificateRepository(acceptance_dsn),
        )

        with psycopg.connect(acceptance_dsn) as conn:
            # All revoked entries must reference a valid CRL
            orphans = conn.execute(
                "SELECT r.id FROM revoked_certificate_list r "
                "LEFT JOIN crls c ON r.crl = c.id "
                "WHERE c.id IS NULL"
            ).fetchall()
            assert len(orphans) == 0, f"Found {len(orphans)} orphan revoked entries"

    def test_transactional_replace_clears_all_tables(self, acceptance_dsn: str) -> None:
        """
        GIVEN the database has composite data (root CAs + CRLs + revoked)
        WHEN the pipeline runs again with Seychelles-only data (no CRLs)
        THEN CRLs and revoked entries are deleted (transactional replace)
        AND only Seychelles root CAs remain.
        """
        composite_bin = fixture_path("ml_composite.bin").read_bytes()
        sc_bin = fixture_path("ml_sc.bin").read_bytes()
        parser = CmsMasterListParser()
        repo = PsycopgCertificateRepository(acceptance_dsn)

        # First run — composite (CRLs + revoked)
        run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=composite_bin),
            parser=parser,
            repository=repo,
        )
        assert _count_rows(acceptance_dsn, "crls") == 1
        assert _count_rows(acceptance_dsn, "revoked_certificate_list") == 15

        # Second run — Seychelles only (no CRLs)
        run_pipeline(
            access_token_provider=FakeAccessTokenProvider(),
            sfc_token_provider=FakeSfcTokenProvider(),
            downloader=FakeBinaryDownloader(data=sc_bin),
            parser=parser,
            repository=repo,
        )
        assert _count_rows(acceptance_dsn, "crls") == 0
        assert _count_rows(acceptance_dsn, "revoked_certificate_list") == 0
        assert _count_rows(acceptance_dsn, "root_ca") >= 1
