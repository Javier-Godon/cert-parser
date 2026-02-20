"""
Domain models — immutable data structures for certificates, CRLs, and metadata.

These are pure value objects with no behavior beyond self-validation.
They represent the data extracted from ICAO Master List CMS bundles
before persistence to PostgreSQL.

All models are frozen dataclasses (immutable) following functional principles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class CertificateRecord:
    """
    Represents a Root CA (CSCA) or Document Signer Certificate (DSC).

    Maps to both the `root_ca` and `dsc` tables (identical schema).
    The `certificate` field holds the raw DER-encoded X.509 certificate.
    """

    certificate: bytes = field(repr=False)
    id: UUID = field(default_factory=uuid4)
    subject_key_identifier: str | None = None
    authority_key_identifier: str | None = None
    issuer: str | None = None
    x_500_issuer: bytes | None = field(default=None, repr=False)
    source: str | None = None
    isn: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CrlRecord:
    """
    Represents a Certificate Revocation List.

    Maps to the `crls` table.
    The `crl` field holds the raw DER-encoded CRL.
    """

    crl: bytes = field(repr=False)
    id: UUID = field(default_factory=uuid4)
    source: str | None = None
    issuer: str | None = None
    country: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RevokedCertificateRecord:
    """
    Represents an individual revoked certificate entry from a CRL.

    Maps to the `revoked_certificate_list` table.
    The `crl` field references the parent CRL's UUID.
    """

    id: UUID = field(default_factory=uuid4)
    source: str | None = None
    country: str | None = None
    isn: str | None = None
    crl: UUID | None = None
    revocation_reason: str | None = None
    revocation_date: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuthCredentials:
    """
    Dual-token credentials for the certificate download service.

    The authentication flow requires two tokens:
      1. access_token — OpenID Connect token (grants access to call services)
      2. sfc_token — Service-specific token (grants access to certificate data)

    Both tokens are required for the final download request:
      - Authorization: Bearer {access_token}
      - x-sfc-authorization: Bearer {sfc_token}
    """

    access_token: str
    sfc_token: str


@dataclass(frozen=True, slots=True)
class MasterListPayload:
    """
    The complete extracted content of an ICAO Master List CMS bundle.

    This is the aggregate returned by the parsing pipeline:
      .bin → CMS unwrap → ML parse → MasterListPayload
    """

    root_cas: list[CertificateRecord] = field(default_factory=list)
    dscs: list[CertificateRecord] = field(default_factory=list)
    crls: list[CrlRecord] = field(default_factory=list)
    revoked_certificates: list[RevokedCertificateRecord] = field(default_factory=list)

    @property
    def total_certificates(self) -> int:
        return len(self.root_cas) + len(self.dscs)

    @property
    def total_items(self) -> int:
        return self.total_certificates + len(self.crls) + len(self.revoked_certificates)
