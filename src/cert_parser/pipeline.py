"""
Pipeline — the core ROP pipeline orchestrating the full workflow.

Domain layer — this is PURE BUSINESS LOGIC. No side effects, no I/O.
All I/O is injected via ports (Protocol interfaces).

The pipeline connects stages via flat_map, forming a railway:

  acquire_access_token()
    → acquire_sfc_token(access_token)
      → build AuthCredentials
        → download(credentials)
          → parse(bin_data)
            → store(payload)

Each stage returns Result[T]. Failures short-circuit automatically
through the ROP railway — no try/except needed.
"""

from __future__ import annotations

from railway.result import Result

from cert_parser.domain.models import AuthCredentials
from cert_parser.domain.ports import (
    AccessTokenProvider,
    BinaryDownloader,
    CertificateRepository,
    MasterListParser,
    SfcTokenProvider,
)


def _build_credentials(
    access_token: str,
    sfc_provider: SfcTokenProvider,
) -> Result[AuthCredentials]:
    """
    Acquire SFC token and combine with access token into AuthCredentials.

    Takes the access_token from step 1, calls SFC login (step 2),
    and packages both tokens into an AuthCredentials value object.
    """
    return sfc_provider.acquire_token(access_token).map(
        lambda sfc_token: AuthCredentials(
            access_token=access_token,
            sfc_token=sfc_token,
        )
    )


def run_pipeline(
    access_token_provider: AccessTokenProvider,
    sfc_token_provider: SfcTokenProvider,
    downloader: BinaryDownloader,
    parser: MasterListParser,
    repository: CertificateRepository,
) -> Result[int]:
    """
    Execute the full ICAO Master List sync pipeline.

    Chains all stages via flat_map — failures short-circuit automatically.

    Flow:
      1. Acquire access token (OpenID Connect password grant)
      2. Acquire SFC token (login with access token + border post config)
      3. Download .bin file (dual-token authentication)
      4. Parse CMS/PKCS#7 structure
      5. Store certificates and CRLs to PostgreSQL

    Returns Result[int] with total rows stored on success,
    or Result.failure with the error from the first failing stage.
    """
    return (
        access_token_provider.acquire_token()
        .flat_map(lambda access_token: _build_credentials(access_token, sfc_token_provider))
        .flat_map(downloader.download)
        .flat_map(parser.parse)
        .flat_map(repository.store)
    )
