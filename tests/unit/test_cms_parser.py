"""
Unit tests for the CMS/PKCS#7 Master List parser adapter.

TDD RED phase — these tests are written BEFORE the implementation.
They define the expected behavior of the CmsMasterListParser class
using real ICAO fixture files extracted from the PKD LDIF data.

Test categories:
  - Happy path: real .bin files → MasterListPayload with expected data
  - Error path: corrupt/empty/truncated → Result.failure(TECHNICAL_ERROR)
  - Metadata correctness: verify SKI, issuer, certificate DER for specific countries
"""

from __future__ import annotations

from uuid import UUID

import pytest
from railway import ErrorCode, ResultAssertions

from cert_parser.adapters.cms_parser import (
    CmsMasterListParser,
    _extract_aki,
    _extract_country_from_issuer,
    _extract_crls,
    _extract_inner_certificates,
    _extract_outer_certificates,
    _extract_ski,
)
from tests.conftest import fixture_path

# ─────────────────────── Fixtures ───────────────────────


@pytest.fixture()
def parser() -> CmsMasterListParser:
    """Create a CmsMasterListParser instance for testing."""
    return CmsMasterListParser()


# ─────────────────────── Happy Path: Small Master Lists ───────────────────────


class TestParseSeychellesMasterList:
    """
    GIVEN a valid Seychelles Master List CMS blob (ml_sc.bin, ~2.9 KB)
    WHEN the parser processes the binary
    THEN it returns a successful Result containing a MasterListPayload.
    """

    def test_returns_success_result(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin (smallest fixture, 1 inner certificate)
        WHEN parsed
        THEN the result is a Success.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_success(result)

    def test_extracts_inner_certificates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin
        WHEN parsed
        THEN root_cas contains at least 1 certificate from the inner Master List.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.root_cas) >= 1

    def test_certificate_has_valid_der_bytes(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin
        WHEN parsed
        THEN each root_ca certificate field contains valid DER bytes (starts with 0x30).
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert isinstance(cert.certificate, bytes)
            assert len(cert.certificate) > 0
            assert cert.certificate[0] == 0x30, (
                "DER-encoded certificate must start with SEQUENCE tag"
            )

    def test_certificate_has_uuid_id(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin
        WHEN parsed
        THEN each certificate record has a valid UUID id.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert isinstance(cert.id, UUID)

    def test_certificate_issuer_contains_seychelles(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin (Seychelles Master List)
        WHEN parsed
        THEN at least one certificate has an issuer containing 'SC' or 'Seychelles'.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        issuers = [c.issuer or "" for c in payload.root_cas]
        assert any("SC" in issuer or "Seychelles" in issuer for issuer in issuers), (
            f"Expected 'SC' or 'Seychelles' in issuers, got: {issuers}"
        )

    def test_certificate_has_subject_key_identifier(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin
        WHEN parsed
        THEN at least one certificate has a non-empty subject_key_identifier (hex string).
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        skis = [c.subject_key_identifier for c in payload.root_cas]
        assert any(ski is not None and len(ski) > 0 for ski in skis), (
            f"Expected at least one non-empty SKI, got: {skis}"
        )


class TestParseFranceMasterList:
    """
    GIVEN a valid France Master List CMS blob (ml_fr.bin, ~117 KB)
    WHEN the parser processes the binary
    THEN it returns a MasterListPayload with many certificates.
    """

    def test_extracts_many_inner_certificates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_fr.bin (France, ~83 inner certificates)
        WHEN parsed
        THEN root_cas contains at least 50 certificates.
        """
        raw_bin = fixture_path("ml_fr.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.root_cas) >= 50, (
            f"Expected ≥50 root CAs from France ML, got {len(payload.root_cas)}"
        )

    def test_all_certificates_have_issuer(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_fr.bin
        WHEN parsed
        THEN every certificate has a non-None issuer string.
        """
        raw_bin = fixture_path("ml_fr.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for i, cert in enumerate(payload.root_cas):
            assert cert.issuer is not None, f"Certificate #{i} has None issuer"
            assert len(cert.issuer) > 0, f"Certificate #{i} has empty issuer"

    def test_total_certificates_property(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_fr.bin
        WHEN parsed
        THEN total_certificates matches root_cas + dscs count.
        """
        raw_bin = fixture_path("ml_fr.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert payload.total_certificates == len(payload.root_cas) + len(payload.dscs)
        assert payload.total_certificates >= 50


class TestParseBangladeshMasterList:
    """
    GIVEN a valid Bangladesh Master List CMS blob (ml_bd.bin, ~4.9 KB)
    WHEN the parser processes the binary
    THEN it returns a MasterListPayload with a small number of certificates.
    """

    def test_extracts_certificates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_bd.bin (Bangladesh, ~2 inner certificates)
        WHEN parsed
        THEN root_cas is non-empty.
        """
        raw_bin = fixture_path("ml_bd.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.root_cas) >= 1

    def test_certificate_has_x500_issuer_bytes(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_bd.bin
        WHEN parsed
        THEN each certificate has x_500_issuer as raw DER bytes.
        """
        raw_bin = fixture_path("ml_bd.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert cert.x_500_issuer is not None
            assert isinstance(cert.x_500_issuer, bytes)
            assert len(cert.x_500_issuer) > 0


class TestParseLargeMasterList:
    """
    GIVEN a large Master List (ml_de.bin, Germany, ~870 KB)
    WHEN the parser processes the binary
    THEN it handles hundreds of certificates without error.
    """

    def test_parses_large_master_list(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_de.bin (Germany, 300+ certificates)
        WHEN parsed
        THEN root_cas contains at least 100 certificates.
        """
        raw_bin = fixture_path("ml_de.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.root_cas) >= 100, (
            f"Expected ≥100 root CAs from Germany ML, got {len(payload.root_cas)}"
        )


# ─────────────────────── CRL Extraction ───────────────────────


class TestCrlExtraction:
    """Tests for CRL extraction from the CMS SignedData.crls field."""

    def test_crls_list_is_present(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN any valid ML .bin
        WHEN parsed
        THEN the crls field is a list (possibly empty — not all MLs contain CRLs).
        """
        raw_bin = fixture_path("ml_fr.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert isinstance(payload.crls, list)


# ──────────── Composite Fixture: Multi-Country + CRLs ────────────


class TestParseCompositeFixture:
    """
    GIVEN ml_composite.bin — a CMS/PKCS#7 SignedData envelope containing:
      - 5 inner CSCA certs (Seychelles + Bangladesh + Botswana)
      - 3 outer ML signer certs
      - 1 Colombia CRL with 15 revoked entries
    WHEN the parser processes this composite blob
    THEN it extracts all data into a MasterListPayload.
    """

    def test_returns_success(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin
        WHEN parsed
        THEN the result is a Success.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_success(result)

    def test_extracts_root_cas_from_inner_and_outer(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin (5 inner + 3 outer = 8 root CAs)
        WHEN parsed
        THEN root_cas contains exactly 8 certificates.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.root_cas) == 8

    def test_extracts_crl_with_correct_country(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin containing 1 Colombia CRL
        WHEN parsed
        THEN crls contains exactly 1 CRL with country='CO'.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.crls) == 1
        assert payload.crls[0].country == "CO"

    def test_crl_has_valid_der_bytes(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin
        WHEN parsed
        THEN the CRL record contains valid DER bytes (starts with 0x30).
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.crls) == 1
        assert payload.crls[0].crl[0] == 0x30

    def test_crl_issuer_mentions_colombia(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin with a Colombia CRL
        WHEN parsed
        THEN the CRL issuer string contains 'Colombia'.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert "Colombia" in (payload.crls[0].issuer or "")

    def test_extracts_15_revoked_certificates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin with a Colombia CRL containing 15 revoked entries
        WHEN parsed
        THEN revoked_certificates contains exactly 15 records.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert len(payload.revoked_certificates) == 15

    def test_revoked_entries_have_country_co(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin with a Colombia CRL
        WHEN parsed
        THEN every revoked certificate has country='CO'.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for revoked in payload.revoked_certificates:
            assert revoked.country == "CO"

    def test_revoked_entries_have_serial_numbers(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin
        WHEN parsed
        THEN every revoked certificate has a non-None hex serial number (isn).
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for revoked in payload.revoked_certificates:
            assert revoked.isn is not None
            assert revoked.isn.startswith("0x")

    def test_revoked_entries_have_revocation_dates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin
        WHEN parsed
        THEN every revoked certificate has a non-None revocation_date.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for revoked in payload.revoked_certificates:
            assert revoked.revocation_date is not None

    def test_revoked_entries_reference_parent_crl(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin
        WHEN parsed
        THEN every revoked certificate's crl UUID matches the CRL record's id.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        crl_id = payload.crls[0].id
        for revoked in payload.revoked_certificates:
            assert revoked.crl == crl_id

    def test_total_items_includes_all_records(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_composite.bin (8 root CAs + 1 CRL + 15 revoked)
        WHEN parsed
        THEN total_items == 8 + 0 + 1 + 15 = 24.
        """
        raw_bin = fixture_path("ml_composite.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        assert payload.total_items == 24


# ─────────────────────── Error Paths ───────────────────────


class TestParseCorruptBinary:
    """
    GIVEN a corrupt binary blob (random bytes, not valid CMS)
    WHEN the parser processes it
    THEN it returns Result.failure with TECHNICAL_ERROR.
    """

    def test_returns_failure(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN corrupt.bin (invalid random bytes)
        WHEN parsed
        THEN the result is a Failure.
        """
        raw_bin = fixture_path("corrupt.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)

    def test_failure_message_mentions_cms(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN corrupt.bin
        WHEN parsed
        THEN the error message references CMS or parsing.
        """
        raw_bin = fixture_path("corrupt.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
        error = result.error()
        assert any(
            keyword in error.message.lower()
            for keyword in ("cms", "parse", "asn1", "invalid", "failed")
        ), f"Expected CMS-related error message, got: {error.message}"


class TestParseEmptyBinary:
    """
    GIVEN an empty binary blob (0 bytes)
    WHEN the parser processes it
    THEN it returns Result.failure with TECHNICAL_ERROR.
    """

    def test_returns_failure(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN empty.bin (0 bytes)
        WHEN parsed
        THEN the result is a Failure.
        """
        raw_bin = fixture_path("empty.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)


class TestParseTruncatedBinary:
    """
    GIVEN a truncated ASN.1 blob (valid header, incomplete data)
    WHEN the parser processes it
    THEN it returns Result.failure with TECHNICAL_ERROR.
    """

    def test_returns_failure(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN truncated.bin (incomplete ASN.1)
        WHEN parsed
        THEN the result is a Failure.
        """
        raw_bin = fixture_path("truncated.bin").read_bytes()
        result = parser.parse(raw_bin)
        ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)


class TestParseRawGarbageBytes:
    """
    GIVEN completely random bytes (not from any file)
    WHEN the parser processes them
    THEN it returns Result.failure with TECHNICAL_ERROR, never raises an exception.
    """

    def test_never_raises(self, parser: CmsMasterListParser) -> None:
        """The parser must NEVER raise — it returns Result.failure instead."""
        result = parser.parse(b"\x00\x01\x02\x03\x04\x05")
        assert result.is_failure()

    def test_empty_bytes_never_raises(self, parser: CmsMasterListParser) -> None:
        """Even zero-length input must return a Result, not raise."""
        result = parser.parse(b"")
        assert result.is_failure()


# ─────────────────────── Metadata Correctness ───────────────────────


class TestMetadataCorrectness:
    """
    Cross-country metadata verification — validate extracted fields
    against known properties of ICAO CSCA certificates.
    """

    def test_serial_number_is_hex_string(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN ml_sc.bin
        WHEN parsed
        THEN each certificate's isn (serial number) is a hex string.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert cert.isn is not None, "Serial number should not be None"
            # Hex string must only contain 0-9, a-f and optional 0x prefix
            isn = cert.isn.lower().removeprefix("0x")
            assert all(c in "0123456789abcdef" for c in isn), (
                f"Serial number should be hex, got: {cert.isn}"
            )

    def test_updated_at_is_none_for_parsed_certificates(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN any parsed ML
        WHEN parsed
        THEN updated_at is None (it's set by the repository, not the parser).
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert cert.updated_at is None

    def test_source_is_set(self, parser: CmsMasterListParser) -> None:
        """
        GIVEN any parsed ML
        WHEN parsed
        THEN each certificate has a non-None source string.
        """
        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result)
        for cert in payload.root_cas:
            assert cert.source is not None
            assert len(cert.source) > 0


# ─────────────────────── Multiple Countries Consistency ───────────────────────


class TestMultipleCountries:
    """Verify the parser works consistently across different country fixtures."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "ml_sc.bin",  # Seychelles — 1 cert
            "ml_bd.bin",  # Bangladesh — 2 certs
            "ml_mn.bin",  # Mongolia — 2 certs
            "ml_fr.bin",  # France — 83 certs
            "ml_it.bin",  # Italy
            "ml_es.bin",  # Spain
            "ml_nl.bin",  # Netherlands
            "ml_ch.bin",  # Switzerland
            "ml_at.bin",  # Austria
            "ml_no.bin",  # Norway
            "ml_composite.bin",  # Composite — 3 countries + CRL
        ],
    )
    def test_parse_returns_success(self, parser: CmsMasterListParser, fixture_name: str) -> None:
        """
        GIVEN a valid ML fixture
        WHEN parsed
        THEN it returns Success with at least 1 root CA.
        """
        path = fixture_path(fixture_name)
        raw_bin = path.read_bytes()
        result = parser.parse(raw_bin)
        payload = ResultAssertions.assert_success(result, f"Failed to parse {fixture_name}")
        assert len(payload.root_cas) >= 1, (
            f"{fixture_name}: expected ≥1 root CA, got {len(payload.root_cas)}"
        )


# ─────────────────────── Edge Cases: None-Check Branches ───────────────────────


class TestExtractOuterCertificatesNone:
    """Tests for _extract_outer_certificates when CMS has no signing certificates."""

    def test_returns_empty_when_certificates_set_is_none(self) -> None:
        """
        GIVEN a SignedData where ['certificates'] is None
        WHEN _extract_outer_certificates is called
        THEN it returns an empty list.
        """
        from asn1crypto import cms

        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        content_info = cms.ContentInfo.load(raw_bin)
        signed_data = content_info["content"]

        # Monkey-patch to simulate None certificates set
        original = signed_data["certificates"]
        signed_data["certificates"] = None
        try:
            result = _extract_outer_certificates(signed_data, source="test")
            assert result == []
        finally:
            signed_data["certificates"] = original


class TestExtractInnerCertificatesNone:
    """Tests for _extract_inner_certificates when CMS has no eContent."""

    def test_returns_empty_when_encap_content_is_none(self) -> None:
        """
        GIVEN a SignedData-like object where encap_content_info.content is None
        WHEN _extract_inner_certificates is called
        THEN it returns an empty list.
        """
        from unittest.mock import MagicMock

        signed_data = MagicMock()
        signed_data.__getitem__ = MagicMock(
            return_value=MagicMock(
                __getitem__=MagicMock(return_value=None),
            ),
        )
        result = _extract_inner_certificates(signed_data, source="test")
        assert result == []


class TestExtractCrlsNone:
    """Tests for _extract_crls when CMS has no CRL set."""

    def test_returns_empty_when_crls_set_is_none(self) -> None:
        """
        GIVEN a SignedData where ['crls'] is None
        WHEN _extract_crls is called
        THEN it returns empty lists for both CRLs and revoked entries.
        """
        from asn1crypto import cms

        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        content_info = cms.ContentInfo.load(raw_bin)
        signed_data = content_info["content"]

        crl_records, revoked_records = _extract_crls(signed_data, source="test")
        assert crl_records == []
        assert revoked_records == []


class TestExtractCountryFromIssuer:
    """Tests for _extract_country_from_issuer helper."""

    def test_extracts_country_from_real_certificate(self) -> None:
        """
        GIVEN an X.509 certificate issuer with C= attribute
        WHEN _extract_country_from_issuer is called
        THEN it returns the 2-letter country code.
        """
        from cryptography import x509 as crypto_x509

        raw_bin = fixture_path("ml_sc.bin").read_bytes()
        parser = CmsMasterListParser()
        payload = ResultAssertions.assert_success(parser.parse(raw_bin))
        cert = crypto_x509.load_der_x509_certificate(payload.root_cas[0].certificate)
        country = _extract_country_from_issuer(cert.issuer)
        assert country is not None
        assert len(country) == 2

    def test_returns_none_for_empty_issuer_attributes(self) -> None:
        """
        GIVEN an X.509 Name with no COUNTRY_NAME OID
        WHEN _extract_country_from_issuer is called
        THEN it returns None.
        """
        from cryptography import x509 as crypto_x509

        # Build a Name with only CN, no C=
        name = crypto_x509.Name(
            [
                crypto_x509.NameAttribute(crypto_x509.oid.NameOID.COMMON_NAME, "Test"),
            ]
        )
        assert _extract_country_from_issuer(name) is None


class TestExtractSkiAkiEdgeCases:
    """Tests for _extract_ski and _extract_aki with edge cases."""

    def test_ski_returns_none_for_cert_without_ski(self) -> None:
        """
        GIVEN a self-signed certificate without SKI extension
        WHEN _extract_ski is called
        THEN it returns None.
        """
        import datetime

        from cryptography import x509 as crypto_x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            crypto_x509.CertificateBuilder()
            .subject_name(
                crypto_x509.Name(
                    [
                        crypto_x509.NameAttribute(crypto_x509.oid.NameOID.COMMON_NAME, "Test"),
                    ]
                )
            )
            .issuer_name(
                crypto_x509.Name(
                    [
                        crypto_x509.NameAttribute(crypto_x509.oid.NameOID.COMMON_NAME, "Test"),
                    ]
                )
            )
            .public_key(key.public_key())
            .serial_number(crypto_x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.UTC))
            .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        assert _extract_ski(cert) is None

    def test_aki_returns_none_for_cert_without_aki(self) -> None:
        """
        GIVEN a self-signed certificate without AKI extension
        WHEN _extract_aki is called
        THEN it returns None.
        """
        import datetime

        from cryptography import x509 as crypto_x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            crypto_x509.CertificateBuilder()
            .subject_name(
                crypto_x509.Name(
                    [
                        crypto_x509.NameAttribute(crypto_x509.oid.NameOID.COMMON_NAME, "Test"),
                    ]
                )
            )
            .issuer_name(
                crypto_x509.Name(
                    [
                        crypto_x509.NameAttribute(crypto_x509.oid.NameOID.COMMON_NAME, "Test"),
                    ]
                )
            )
            .public_key(key.public_key())
            .serial_number(crypto_x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.UTC))
            .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        assert _extract_aki(cert) is None
