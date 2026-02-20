"""
CMS/Master List parser adapter — CMS unwrapping + X.509 extraction.

Adapter layer — implements MasterListParser port using:
  - asn1crypto: CMS/PKCS#7 envelope unwrapping (eContent, certificates, CRLs)
  - cryptography (PyCA): X.509 certificate metadata extraction (SKI, AKI, issuer)

Pipeline:
  raw .bin bytes
    → asn1crypto: ContentInfo.load() → SignedData → encap_content_info
    → asn1crypto: parse ICAO Master List ASN.1 structure (certList)
    → cryptography: x509.load_der_x509_certificate() for metadata
    → MasterListPayload (domain model)

Key design decision: asn1crypto handles the CMS envelope (it's the only Python
library that exposes eContent, certificates, and CRLs from SignedData).
cryptography handles X.509 metadata extraction (best-in-class typed API).
"""

from __future__ import annotations

import uuid

import structlog
from asn1crypto import cms, core
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.x509.extensions import ExtensionNotFound
from railway import ErrorCode
from railway.result import Result

from cert_parser.domain.models import (
    CertificateRecord,
    CrlRecord,
    MasterListPayload,
    RevokedCertificateRecord,
)

log = structlog.get_logger()

# ─────────────────────── ICAO ASN.1 Schema ───────────────────────
# OID: 2.23.136.1.1.2 (id-icao-mrtd-security-masterlist)
#
# CscaMasterList ::= SEQUENCE {
#     version    INTEGER,
#     certList   SET OF Certificate
# }


class _CertificateSet(core.SetOf):  # type: ignore[misc]
    """ASN.1 SET OF Certificate — the certList inside CscaMasterList."""

    _child_spec = asn1_x509.Certificate


class _CscaMasterList(core.Sequence):  # type: ignore[misc]
    """ASN.1 SEQUENCE for the ICAO Master List inner structure."""

    _fields = [
        ("version", core.Integer),
        ("cert_list", _CertificateSet),
    ]


# ─────────────────────── X.509 Metadata Extraction ───────────────────────


def _extract_ski(cert: x509.Certificate) -> str | None:
    """Extract Subject Key Identifier extension as hex string, or None if absent."""
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        return ext.value.digest.hex()
    except ExtensionNotFound, ValueError:
        return None


def _extract_aki(cert: x509.Certificate) -> str | None:
    """Extract Authority Key Identifier extension as hex string, or None if absent."""
    try:
        ext = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
        if ext.value.key_identifier is not None:
            return ext.value.key_identifier.hex()
        return None
    except ExtensionNotFound, ValueError:
        return None


def _der_to_certificate_record(
    der_bytes: bytes,
    source: str,
) -> CertificateRecord:
    """
    Convert DER-encoded X.509 bytes into a CertificateRecord.

    Uses cryptography for metadata extraction. Missing extensions
    (SKI, AKI) result in None fields — they do NOT cause failures.
    """
    cert = x509.load_der_x509_certificate(der_bytes)
    issuer_str = cert.issuer.rfc4514_string()
    x500_issuer_bytes = cert.issuer.public_bytes()
    serial_hex = hex(cert.serial_number)
    ski = _extract_ski(cert)
    aki = _extract_aki(cert)

    if ski is None:
        log.warning("certificate.missing_ski", issuer=issuer_str, serial=serial_hex)

    return CertificateRecord(
        certificate=der_bytes,
        subject_key_identifier=ski,
        authority_key_identifier=aki,
        issuer=issuer_str,
        x_500_issuer=x500_issuer_bytes,
        source=source,
        isn=serial_hex,
    )


# ─────────────────────── CMS Unwrapping ───────────────────────


def _extract_outer_certificates(
    signed_data: cms.SignedData,
    source: str,
) -> list[CertificateRecord]:
    """Extract certificates from SignedData.certificates (outer CMS envelope signers)."""
    certs_set = signed_data["certificates"]
    if certs_set is None:
        return []

    records: list[CertificateRecord] = []
    for cert_choice in certs_set:
        der_bytes = cert_choice.chosen.dump()
        records.append(_der_to_certificate_record(der_bytes, source=source))
    return records


def _extract_inner_certificates(
    signed_data: cms.SignedData,
    source: str,
) -> list[CertificateRecord]:
    """
    Extract certificates from the CscaMasterList inside the CMS eContent.

    The eContent is an OCTET STRING containing:
      CscaMasterList ::= SEQUENCE { version INTEGER, certList SET OF Certificate }
    """
    encap_content = signed_data["encap_content_info"]["content"]
    if encap_content is None:
        return []

    # The eContent is wrapped in an OCTET STRING — get the raw bytes
    inner_bytes = encap_content.native

    # Parse as CscaMasterList
    master_list = _CscaMasterList.load(inner_bytes)
    cert_list = master_list["cert_list"]

    records: list[CertificateRecord] = []
    for asn1_cert in cert_list:
        der_bytes = asn1_cert.dump()
        records.append(_der_to_certificate_record(der_bytes, source=source))
    return records


def _extract_country_from_issuer(issuer: x509.Name) -> str | None:
    """Extract the C= (country) attribute from an X.509 issuer Name."""
    for name_attr in issuer:
        if name_attr.oid == x509.oid.NameOID.COUNTRY_NAME:
            return name_attr.value  # type: ignore[no-any-return]
    return None


def _build_revoked_record(
    revoked_cert: x509.RevokedCertificate,
    crl_id: uuid.UUID | None,
    source: str,
    country: str | None,
) -> RevokedCertificateRecord:
    """Build a RevokedCertificateRecord from a single revoked certificate entry."""
    reason = None
    try:
        reason_ext = revoked_cert.extensions.get_extension_for_class(x509.CRLReason)
        reason = reason_ext.value.reason.value
    except ExtensionNotFound, ValueError:
        pass

    return RevokedCertificateRecord(
        source=source,
        country=country,
        isn=hex(revoked_cert.serial_number),
        crl=crl_id,
        revocation_reason=reason,
        revocation_date=revoked_cert.revocation_date_utc,
    )


def _parse_single_crl(
    crl_der: bytes,
    source: str,
) -> tuple[CrlRecord, list[RevokedCertificateRecord]]:
    """Parse a single DER-encoded CRL into a CrlRecord + its revoked entries."""
    crl_obj = x509.load_der_x509_crl(crl_der)
    issuer_str = crl_obj.issuer.rfc4514_string()
    country = _extract_country_from_issuer(crl_obj.issuer)

    crl_record = CrlRecord(
        crl=crl_der,
        source=source,
        issuer=issuer_str,
        country=country,
    )

    revoked_records = [
        _build_revoked_record(revoked_cert, crl_record.id, source, country)
        for revoked_cert in crl_obj
    ]

    return crl_record, revoked_records


def _extract_crls(
    signed_data: cms.SignedData,
    source: str,
) -> tuple[list[CrlRecord], list[RevokedCertificateRecord]]:
    """Extract CRLs and revoked certificate entries from SignedData.crls."""
    crls_set = signed_data["crls"]
    if crls_set is None:
        return [], []

    crl_records: list[CrlRecord] = []
    revoked_records: list[RevokedCertificateRecord] = []

    for crl_choice in crls_set:
        crl_der = crl_choice.chosen.dump()
        crl_record, revoked = _parse_single_crl(crl_der, source)
        crl_records.append(crl_record)
        revoked_records.extend(revoked)

    return crl_records, revoked_records


# ─────────────────────── Public Parser Class ───────────────────────


class CmsMasterListParser:
    """
    Parse raw CMS/PKCS#7 binary into a MasterListPayload.

    Implements the MasterListParser port.
    All exceptions are caught at this adapter boundary via Result.from_computation().
    """

    def parse(self, raw_bin: bytes) -> Result[MasterListPayload]:
        """
        Parse a raw .bin (CMS/PKCS#7 SignedData) into a MasterListPayload.

        Extraction pipeline:
          1. Load CMS ContentInfo envelope (asn1crypto)
          2. Extract SignedData
          3. Extract outer certificates (CMS signers)
          4. Extract inner certificates (CscaMasterList.certList)
          5. Extract CRLs + revoked entries
          6. Build MasterListPayload

        Returns Result[MasterListPayload] on success.
        Returns Result.failure(TECHNICAL_ERROR, ...) on any parsing failure.
        """
        return Result.from_computation(
            lambda: self._do_parse(raw_bin),
            ErrorCode.TECHNICAL_ERROR,
            "Failed to parse CMS Master List binary",
        )

    def _do_parse(self, raw_bin: bytes) -> MasterListPayload:
        """
        Internal parse — may raise exceptions (caught by from_computation).

        This is the only method that performs actual I/O-like work.
        """
        source = "icao-masterlist"

        # Step 1: Load CMS ContentInfo
        content_info = cms.ContentInfo.load(raw_bin)
        signed_data = content_info["content"]

        # Step 2: Extract outer certificates (CMS envelope signers)
        outer_certs = _extract_outer_certificates(signed_data, source=source)

        # Step 3: Extract inner certificates (Master List payload)
        inner_certs = _extract_inner_certificates(signed_data, source=source)

        # Step 4: Extract CRLs
        crl_records, revoked_records = _extract_crls(signed_data, source=source)

        # Combine outer + inner as root CAs
        all_root_cas = inner_certs + outer_certs

        log.info(
            "parser.complete",
            inner_certs=len(inner_certs),
            outer_certs=len(outer_certs),
            total_root_cas=len(all_root_cas),
            crls=len(crl_records),
            revoked=len(revoked_records),
        )

        return MasterListPayload(
            root_cas=all_root_cas,
            crls=crl_records,
            revoked_certificates=revoked_records,
        )
