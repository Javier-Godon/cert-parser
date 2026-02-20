"""
Ports — Protocol-based interfaces for infrastructure adapters.

These define WHAT the application needs (contracts) without specifying
HOW it's done (implementation). Following hexagonal architecture:

  Domain ← Ports (protocols) ← Adapters (implementations)

Each port is a Protocol (structural typing) so adapters satisfy
the contract simply by implementing the methods — no inheritance.

Authentication flow (dual-token):
  1. AccessTokenProvider → OpenID Connect token (general access)
  2. SfcTokenProvider    → Service-specific token (certificate access)
  3. BinaryDownloader    → Download using both tokens (AuthCredentials)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from railway.result import Result

from cert_parser.domain.models import AuthCredentials, MasterListPayload


@runtime_checkable
class AccessTokenProvider(Protocol):
    """
    Port: obtain an OpenID Connect access token via password grant.

    This is the FIRST step of the dual-token authentication flow.
    The access token grants permission to call other services (including login).

    Returns Result[str] where str is the bearer access_token.
    """

    def acquire_token(self) -> Result[str]: ...


@runtime_checkable
class SfcTokenProvider(Protocol):
    """
    Port: obtain an SFC service token via the login endpoint.

    This is the SECOND step of the dual-token authentication flow.
    Requires the access_token from step 1 as a Bearer authorization header,
    plus border post configuration (borderPostId, boxId, passengerControlType).

    Returns Result[str] where str is the SFC bearer token.
    """

    def acquire_token(self, access_token: str) -> Result[str]: ...


@runtime_checkable
class BinaryDownloader(Protocol):
    """
    Port: download the .bin Master List bundle using dual-token credentials.

    Requires AuthCredentials containing both:
      - access_token  → sent as Authorization: Bearer {access_token}
      - sfc_token     → sent as x-sfc-authorization: Bearer {sfc_token}
    """

    def download(self, credentials: AuthCredentials) -> Result[bytes]: ...


@runtime_checkable
class MasterListParser(Protocol):
    """
    Port: parse a raw .bin (CMS/PKCS#7) into a MasterListPayload.

    The implementation handles:
      1. CMS/PKCS#7 envelope unwrapping
      2. ICAO Master List ASN.1 structure parsing
      3. X.509 certificate and CRL extraction
      4. Metadata extraction (SKI, AKI, issuer, etc.)
    """

    def parse(self, raw_bin: bytes) -> Result[MasterListPayload]: ...


@runtime_checkable
class CertificateRepository(Protocol):
    """
    Port: atomically replace all certificate data in the database.

    The implementation uses a TRANSACTIONAL REPLACE pattern:
      1. BEGIN transaction
      2. DELETE all existing rows from all tables (FK-safe order)
      3. INSERT new rows from the MasterListPayload
      4. COMMIT (or automatic ROLLBACK on any failure)

    This guarantees old data is preserved if the insert fails.
    """

    def store(self, payload: MasterListPayload) -> Result[int]:
        """
        Atomically replace all stored data with the given payload.

        Returns Result[int] with total rows affected on success.
        On failure, old data remains intact (transaction rolled back).
        """
        ...
