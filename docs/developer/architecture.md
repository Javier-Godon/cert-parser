# Architecture — Hexagonal / Ports & Adapters

## Overview

cert-parser follows **Hexagonal Architecture** (also called Ports & Adapters). The central idea: business logic lives in the center (domain + pipeline), infrastructure concerns live at the edges (adapters), and **protocols** define the contracts between them.

```
                    ┌──────────────────────────────────┐
                    │         Composition Root          │
                    │           (main.py)               │
                    └────────────────┬─────────────────┘
                                     │ creates & wires
                    ┌────────────────▼─────────────────┐
                    │          Pipeline Layer           │
                    │         (pipeline.py)             │
                    │  flat_map chain, pure logic only  │
                    └─────────┬───────────┬────────────┘
                              │ depends on│
                    ┌─────────▼───────────▼────────────┐
                    │         Domain Layer              │
                    │    models.py  +  ports.py         │
                    │  Value objects + Protocol ifaces  │
                    └─────────▲───────────▲────────────┘
                              │ implements│
                    ┌─────────┴───────────┴────────────┐
                    │         Adapter Layer             │
                    │  http_client.py  │  cms_parser.py │
                    │             repository.py         │
                    └──────────────────────────────────┘
```

## Import Direction

The **non-negotiable** import rule:

```
main.py  →  pipeline.py  →  domain/  ←  adapters/
```

- **Domain** NEVER imports from adapters
- **Pipeline** imports from domain only (ports, models)
- **Adapters** import from domain (to implement ports, use models)
- **Main** imports from everything (it's the composition root)

This ensures the domain layer has zero coupling to infrastructure and can be tested in complete isolation.

## Layer Responsibilities

### Domain Layer (`domain/`)

**Files**: `models.py`, `ports.py`

**Rules**:
- PURE — no I/O, no side effects, no database, no HTTP
- Contains frozen dataclasses (value objects) and Protocol interfaces (ports)
- Zero dependencies on external libraries (only stdlib + railway)

**models.py** defines four immutable data structures:

| Model | Table | Purpose |
|-------|-------|---------|
| `CertificateRecord` | `root_ca`, `dsc` | X.509 certificate + extracted metadata |
| `CrlRecord` | `crls` | Certificate Revocation List |
| `RevokedCertificateRecord` | `revoked_certificate_list` | Individual revoked entries |
| `MasterListPayload` | (aggregate) | Everything extracted from a CMS bundle |

**ports.py** defines five Protocol interfaces:

| Port | Method | Signature |
|------|--------|-----------|
| `AccessTokenProvider` | `acquire_token()` | `→ Result[str]` |
| `SfcTokenProvider` | `acquire_token(access_token)` | `→ Result[str]` |
| `BinaryDownloader` | `download(credentials)` | `→ Result[bytes]` |
| `MasterListParser` | `parse(raw_bin)` | `→ Result[MasterListPayload]` |
| `CertificateRepository` | `store(payload)` | `→ Result[int]` |

The authentication flow uses a **dual-token** pattern: `AccessTokenProvider` acquires an OpenID Connect access token (Step 1), `SfcTokenProvider` uses that token to acquire an SFC service token (Step 2), and `BinaryDownloader` sends both tokens as headers (Step 3).

### Pipeline Layer (`pipeline.py`)

**Single function**: `run_pipeline()`

This is **PURE business logic** — zero I/O. It chains the five stages via `flat_map`:

```python
def run_pipeline(
    access_token_provider: AccessTokenProvider,
    sfc_token_provider: SfcTokenProvider,
    downloader: BinaryDownloader,
    parser: MasterListParser,
    repository: CertificateRepository,
) -> Result[int]:
    return (
        access_token_provider.acquire_token()
        .flat_map(lambda access_token: _build_credentials(access_token, sfc_token_provider))
        .flat_map(downloader.download)
        .flat_map(parser.parse)
        .flat_map(repository.store)
    )
```

The helper `_build_credentials()` acquires the SFC token and packages both tokens into an `AuthCredentials` value object. Each stage returns `Result[T]`. If any stage fails, the failure propagates automatically through the railway — no try/except needed.

### Adapter Layer (`adapters/`)

**Files**: `http_client.py`, `cms_parser.py`, `repository.py`

These are the ONLY places where:
- Exceptions are caught (via `Result.from_computation()`)
- Real I/O happens (HTTP calls, file parsing, database queries)
- External libraries are used (httpx, asn1crypto, cryptography, psycopg)

Each adapter class implements a domain port by having the right method signature.

### Composition Root (`main.py`)

**Responsibilities**:
1. Configure structlog for structured logging
2. Load `AppSettings` from environment
3. Create concrete adapter instances (`_create_adapters()`)
4. Wire the pipeline via `functools.partial`
5. Create and start the scheduler

This is the ONLY file that knows about concrete implementations. Everything else depends on abstractions (Protocol interfaces).

## Dependency Injection

No DI framework is used. The pipeline function receives its dependencies as parameters:

```python
# main.py — wires concrete adapters into the pipeline
pipeline_fn = partial(
    run_pipeline,
    access_token_provider=access_token_provider,  # HttpAccessTokenProvider
    sfc_token_provider=sfc_token_provider,        # HttpSfcTokenProvider
    downloader=downloader,                        # HttpBinaryDownloader
    parser=parser,                                # CmsMasterListParser
    repository=repository,                        # PsycopgCertificateRepository
)
```

For testing, inject mock ports:

```python
# test_pipeline.py — inject fake adapters
result = run_pipeline(
    access_token_provider=MockAccessTokenProvider(),
    sfc_token_provider=MockSfcTokenProvider(),
    downloader=MockDownloader(),
    parser=MockParser(),
    repository=MockRepository(),
)
```

## Why Hexagonal Architecture?

1. **Testability** — the pipeline can be tested with mock ports, no real HTTP/DB needed
2. **Replaceability** — swap adapters without changing business logic (e.g., different HTTP client)
3. **Clarity** — strict layer boundaries make the codebase navigable
4. **Safety** — the domain layer is guaranteed pure, so reasoning about it is trivial

## Design Decisions

### Why Protocol over ABC?

Python's `Protocol` (PEP 544) enables **structural typing** — an adapter satisfies a port simply by having the right methods. No need for explicit inheritance:

```python
# This class implements AccessTokenProvider without knowing AccessTokenProvider exists
class HttpAccessTokenProvider:
    def acquire_token(self) -> Result[str]: ...
```

### Why `partial` over a Pipeline class?

The pipeline is a single function. Using `functools.partial` to pre-fill the adapter arguments is simpler than creating a class with constructor injection. The function is pure — it doesn't hold state.

### Why separate `main.py` from `scheduler.py`?

`scheduler.py` is reusable infrastructure (could schedule any job). `main.py` is the composition root specific to this application. This separation keeps the scheduler testable without requiring real adapters.
