"""
PostgreSQL repository adapter — certificate and CRL persistence.

Adapter layer — implements CertificateRepository port using psycopg (v3)
for sync PostgreSQL access with parameterized queries.

Uses TRANSACTIONAL REPLACE pattern:
  1. BEGIN transaction
  2. DELETE all rows (FK-safe order: child → parent)
  3. INSERT all rows from the MasterListPayload
  4. COMMIT (or automatic ROLLBACK on failure → old data preserved)

Table mapping:
  CertificateRecord → root_ca table (inner + outer CSCA certs)
  CertificateRecord → dsc table (document signer certs)
  CrlRecord          → crls table
  RevokedCertificateRecord → revoked_certificate_list table

No ORM — raw parameterized SQL for maximum control and transparency.
"""

from __future__ import annotations

from typing import Any

import psycopg
import structlog
from railway import ErrorCode
from railway.result import Result

from cert_parser.domain.models import (
    CertificateRecord,
    CrlRecord,
    MasterListPayload,
    RevokedCertificateRecord,
)

log = structlog.get_logger()

_INSERT_ROOT_CA = """
INSERT INTO certs.root_ca (
    id, certificate, subject_key_identifier, authority_key_identifier,
    issuer, master_list_issuer, x_500_issuer, source, isn, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_DSC = """
INSERT INTO certs.dsc (
    id, certificate, subject_key_identifier, authority_key_identifier,
    issuer, x_500_issuer, source, isn, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_CRL = """
INSERT INTO certs.crls (id, crl, source, issuer, country, updated_at)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_INSERT_REVOKED = """
INSERT INTO certs.revoked_certificate_list (
    id, source, country, isn, crl, revocation_reason, revocation_date, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


class PsycopgCertificateRepository:
    """
    Persist certificate data to PostgreSQL using transactional replace.

    Implements the CertificateRepository port.
    All exceptions are caught at this adapter boundary via Result.from_computation().
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def store(self, payload: MasterListPayload) -> Result[int]:
        """
        Atomically replace all stored data with the given payload.

        Returns Result[int] with total rows affected on success.
        On failure, old data remains intact (transaction rolled back).
        """
        return Result.from_computation(
            lambda: self._transactional_replace(payload),
            ErrorCode.DATABASE_ERROR,
            "Failed to persist certificates to database",
        )

    def _transactional_replace(self, payload: MasterListPayload) -> int:
        """
        DELETE all → INSERT all in a single ACID transaction.

        If any exception occurs, psycopg rolls back automatically
        and the old data remains intact.
        """
        with psycopg.connect(self._dsn) as conn, conn.transaction(), conn.cursor() as cur:
            self._delete_all(cur)
            rows = self._insert_all(cur, payload)
            log.info(
                "repository.stored",
                root_cas=len(payload.root_cas),
                dscs=len(payload.dscs),
                crls=len(payload.crls),
                revoked=len(payload.revoked_certificates),
                total_rows=rows,
            )
            return rows

    def _delete_all(self, cur: psycopg.Cursor[Any]) -> None:
        """Delete all rows in FK-safe order: child → parent."""
        cur.execute("DELETE FROM certs.revoked_certificate_list")
        cur.execute("DELETE FROM certs.crls")
        cur.execute("DELETE FROM certs.dsc")
        cur.execute("DELETE FROM certs.root_ca")

    def _insert_all(self, cur: psycopg.Cursor[Any], payload: MasterListPayload) -> int:
        """Insert all records from the payload, returning total row count."""
        rows = 0
        rows += self._insert_root_cas(cur, payload.root_cas)
        rows += self._insert_dscs(cur, payload.dscs)
        rows += self._insert_crls(cur, payload.crls)
        rows += self._insert_revoked(cur, payload.revoked_certificates)
        return rows

    def _insert_root_cas(
        self,
        cur: psycopg.Cursor[Any],
        certs: list[CertificateRecord],
    ) -> int:
        """Insert root CA certificate records (includes master_list_issuer)."""
        for cert in certs:
            cur.execute(
                _INSERT_ROOT_CA,
                (
                    cert.id,
                    cert.certificate,
                    cert.subject_key_identifier,
                    cert.authority_key_identifier,
                    cert.issuer,
                    cert.master_list_issuer,
                    cert.x_500_issuer,
                    cert.source,
                    cert.isn,
                    cert.updated_at,
                ),
            )
        return len(certs)

    def _insert_dscs(
        self,
        cur: psycopg.Cursor[Any],
        certs: list[CertificateRecord],
    ) -> int:
        """Insert DSC certificate records."""
        for cert in certs:
            cur.execute(
                _INSERT_DSC,
                (
                    cert.id,
                    cert.certificate,
                    cert.subject_key_identifier,
                    cert.authority_key_identifier,
                    cert.issuer,
                    cert.x_500_issuer,
                    cert.source,
                    cert.isn,
                    cert.updated_at,
                ),
            )
        return len(certs)

    def _insert_crls(self, cur: psycopg.Cursor[Any], crls: list[CrlRecord]) -> int:
        """Insert CRL records."""
        for crl in crls:
            cur.execute(
                _INSERT_CRL,
                (crl.id, crl.crl, crl.source, crl.issuer, crl.country, crl.updated_at),
            )
        return len(crls)

    def _insert_revoked(
        self,
        cur: psycopg.Cursor[Any],
        revoked: list[RevokedCertificateRecord],
    ) -> int:
        """Insert revoked certificate records."""
        for rec in revoked:
            cur.execute(
                _INSERT_REVOKED,
                (
                    rec.id,
                    rec.source,
                    rec.country,
                    rec.isn,
                    rec.crl,
                    rec.revocation_reason,
                    rec.revocation_date,
                    rec.updated_at,
                ),
            )
        return len(revoked)
