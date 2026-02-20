"""
Unit tests for domain models — value objects.

Verifies frozen dataclass behavior, default factories,
and computed properties.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from cert_parser.domain.models import (
    CertificateRecord,
    CrlRecord,
    MasterListPayload,
    RevokedCertificateRecord,
)


class TestCertificateRecord:
    """Verify CertificateRecord value object behavior."""

    def test_certificate_bytes_required(self) -> None:
        """
        GIVEN a CertificateRecord
        WHEN created with certificate bytes
        THEN the bytes are stored correctly.
        """
        cert = CertificateRecord(certificate=b"\x30\x00")
        assert cert.certificate == b"\x30\x00"

    def test_default_uuid_generated(self) -> None:
        """
        GIVEN a CertificateRecord with no explicit id
        WHEN created
        THEN a UUID is generated automatically.
        """
        cert = CertificateRecord(certificate=b"\x30\x00")
        assert isinstance(cert.id, UUID)

    def test_frozen_prevents_mutation(self) -> None:
        """
        GIVEN a frozen CertificateRecord
        WHEN attempting to modify a field
        THEN FrozenInstanceError is raised.
        """
        cert = CertificateRecord(certificate=b"\x30\x00")
        with pytest.raises(AttributeError):
            cert.issuer = "modified"  # type: ignore[misc]

    def test_optional_fields_default_to_none(self) -> None:
        """
        GIVEN a CertificateRecord with only required fields
        WHEN accessed
        THEN optional fields are None.
        """
        cert = CertificateRecord(certificate=b"\x30\x00")
        assert cert.issuer is None
        assert cert.subject_key_identifier is None
        assert cert.authority_key_identifier is None
        assert cert.x_500_issuer is None
        assert cert.source is None
        assert cert.isn is None
        assert cert.updated_at is None


class TestMasterListPayload:
    """Verify MasterListPayload aggregate and computed properties."""

    def test_total_certificates_counts_root_cas_and_dscs(self) -> None:
        """
        GIVEN a payload with 2 root CAs and 1 DSC
        WHEN total_certificates is accessed
        THEN it returns 3.
        """
        payload = MasterListPayload(
            root_cas=[CertificateRecord(certificate=b"a"), CertificateRecord(certificate=b"b")],
            dscs=[CertificateRecord(certificate=b"c")],
        )
        assert payload.total_certificates == 3

    def test_total_items_includes_all(self) -> None:
        """
        GIVEN a payload with root CAs, DSCs, CRLs, and revoked certs
        WHEN total_items is accessed
        THEN it returns the sum of all lists.
        """
        payload = MasterListPayload(
            root_cas=[CertificateRecord(certificate=b"a")],
            dscs=[CertificateRecord(certificate=b"b")],
            crls=[CrlRecord(crl=b"c")],
            revoked_certificates=[RevokedCertificateRecord(), RevokedCertificateRecord()],
        )
        assert payload.total_items == 5

    def test_empty_payload(self) -> None:
        """
        GIVEN an empty payload
        WHEN total_certificates and total_items are accessed
        THEN both return 0.
        """
        payload = MasterListPayload()
        assert payload.total_certificates == 0
        assert payload.total_items == 0
