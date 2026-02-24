# AI Coding Instructions — cert-parser

> These instructions govern ALL AI-assisted code generation in this project.
> Every file, function, class, and test MUST conform to these principles.

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Name** | cert-parser |
| **Purpose** | Download ICAO Master List `.bin` bundles via REST, extract X.509 certificates and CRLs from CMS/PKCS#7 structures, persist to PostgreSQL |
| **Python** | 3.14+ (use all modern features: `match/case`, `type` aliases, `X \| Y` unions) |
| **Paradigm** | Functional / Railway-Oriented Programming (ROP) |
| **Framework** | `railway-rop` (local, under `python_framework/`) |
| **Core Mandate** | **Simplicity & readability above all** — if the code is not immediately understandable, it is wrong |

---

## 2. Foundational Principles — Railway-Oriented Programming

### 2.1 The Railway Metaphor

Every operation in this codebase runs on a **two-track railway**:

```
  ┌───────────┐  flat_map  ┌───────────┐  flat_map  ┌───────────┐  flat_map  ┌──────────┐  flat_map  ┌──────────┐
  │ acquire   │──Success──│ acquire   │──Success──│ download  │──Success──│  parse   │──Success──│  store   │──→ Result[T]
  │ access    │           │ sfc token │           │   .bin    │           │    ML    │           │  to DB   │
  │ token     │           │ + build   │           │ (dual hdr)│           │          │           │          │
  └─────┬─────┘           │ creds     │           └─────┬─────┘           └─────┬────┘           └─────┬────┘
        │ Failure         └─────┬─────┘                 │ Failure               │ Failure               │ Failure
        └───────────────────────┴───────────────────────┴───────────────────────┴───────────────────────┴──→ Result[T]
```

- **Success track**: data flows forward through `flat_map` / `map`
- **Failure track**: errors propagate automatically — NO try/except in business logic
- **ALL public functions** return `Result[T]`, never raise exceptions

### 2.2 Core Rules (NON-NEGOTIABLE)

1. **NEVER** use `try/except` in business logic. Use `Result.from_computation()` at adapter boundaries.
2. **NEVER** return `None` to indicate failure. Return `Result.failure()`.
3. **NEVER** raise exceptions in pure functions. Return `Result.failure()`.
4. **ALWAYS** return `Result[T]` from any function that can fail.
5. **ALWAYS** use `flat_map` to chain Result-returning functions.
6. **ALWAYS** use `map` to transform success values with infallible functions.
7. **ALWAYS** use `ensure` for validation predicates.
8. **ALWAYS** use `peek` for logging/side-effects that don't alter the result.
9. **ALWAYS** use `either` or `match/case` for final result consumption.
10. **PREFER** `ResultFailures` factory methods over raw `Result.failure()`.

### 2.3 Error Codes — Use the Right One

```python
from railway import ErrorCode

# Map to these codes:
ErrorCode.AUTHENTICATION_ERROR   # Token acquisition failures
ErrorCode.EXTERNAL_SERVICE_ERROR  # REST download failures, HTTP errors
ErrorCode.VALIDATION_ERROR        # Malformed .bin, invalid CMS structure
ErrorCode.TECHNICAL_ERROR         # CMS parsing / ASN.1 decoding failures
ErrorCode.DATABASE_ERROR          # PostgreSQL connection / query failures
ErrorCode.CONFIGURATION_ERROR     # Missing env vars, bad config
ErrorCode.TIMEOUT_ERROR           # HTTP or DB timeouts
```

---

## 3. Architecture — Hexagonal / Ports & Adapters

### 3.1 Layer Rules

```
src/cert_parser/
├── domain/           # PURE — no I/O, no imports from adapters
│   ├── models.py     # Frozen dataclasses (value objects)
│   └── ports.py      # Protocol interfaces (what we need)
├── adapters/         # IMPURE — I/O lives here
│   ├── http_client.py    # httpx: AccessTokenProvider + SfcTokenProvider + BinaryDownloader
│   ├── cms_parser.py     # asn1crypto + cryptography: MasterListParser
│   └── repository.py     # psycopg: CertificateRepository
├── pipeline.py       # PURE — orchestrates domain via flat_map chains
├── scheduler.py      # Infrastructure — APScheduler wiring
├── config.py         # pydantic-settings configuration
└── main.py           # Composition root — wires everything
```

**Import direction**: `main → pipeline → domain ← adapters`. Domain NEVER imports from adapters.

### 3.2 Dependency Injection

- **Ports** are `Protocol` classes (structural typing) — no ABC, no inheritance
- **Adapters** implement ports by having the right method signatures
- **Composition root** (`main.py`) is the ONLY place that creates concrete adapters
- **Pipeline** receives ports as constructor arguments, never creates adapters

```python
# ✅ Correct — depends on Protocol
def run_pipeline(
    access_token_provider: AccessTokenProvider,
    sfc_token_provider: SfcTokenProvider,
    downloader: BinaryDownloader,
    parser: MasterListParser,
    repository: CertificateRepository,
) -> Result[int]:
    return (
        access_token_provider.acquire_token()
        .flat_map(lambda token: _build_credentials(token, sfc_token_provider))
        .flat_map(downloader.download)
        .flat_map(parser.parse)
        .flat_map(repository.store)
    )

# ❌ Wrong — depends on concrete class
def run_pipeline():
    client = HttpClient(settings)  # DO NOT instantiate adapters here
```

---

## 4. Coding Standards

### 4.1 Python Style

- **Type hints everywhere** — mypy strict mode, no `Any` unless truly unavoidable
- **Frozen dataclasses** for all value objects (`@dataclass(frozen=True, slots=True)`)
- **`match/case`** for Result destructuring (Python 3.10+)
- **`X | Y`** union syntax, not `Union[X, Y]` (Python 3.10+)
- **`from __future__ import annotations`** in every file
- **ruff** for linting and formatting (line length 100)
- **No mutable global state** — configuration is injected, not imported

### 4.2 Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `cms_parser.py` |
| Classes | `PascalCase` | `CertificateRecord` |
| Functions | `snake_case` | `acquire_token` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| Type aliases | `PascalCase` | `CertBytes = bytes` |
| Protocols | `PascalCase` (noun/role) | `AccessTokenProvider` |
| Result factories | `verb_noun` | `ResultFailures.validation_error()` |

### 4.3 Docstrings

Every module, class, and public function MUST have a docstring:

```python
def acquire_token(self) -> Result[str]:
    """
    Request an access token from the OpenID Connect endpoint.

    Calls POST {auth_url} with resource owner password grant.
    Returns Result[str] with the access_token on success,
    or Result.failure(AUTHENTICATION_ERROR, ...) on any HTTP or auth error.
    """
```

### 4.4 Module Header

Every `.py` file starts with a module docstring explaining:
1. What this module does
2. Which architectural layer it belongs to
3. Key design decisions

---

## 5. Technology Stack — Usage Patterns

### 5.1 httpx (REST Client)

```python
# ✅ Use sync client with context manager
with httpx.Client(timeout=timeout) as client:
    response = client.post(url, json=payload)

# ✅ Wrap in Result.from_computation at adapter boundary
def acquire_token(self) -> Result[str]:
    """Step 1: OpenID Connect password grant → access_token."""
    return Result.from_computation(
        lambda: self._do_token_request(),
        ErrorCode.AUTHENTICATION_ERROR,
        "Failed to acquire access token",
    )

def acquire_token(self, access_token: str) -> Result[str]:
    """Step 2: SFC login with bearer + JSON body → sfc_token."""
    return Result.from_computation(
        lambda: self._do_login_request(access_token),
        ErrorCode.AUTHENTICATION_ERROR,
        "Failed to acquire SFC token",
    )

# ✅ Download with dual-token headers
with client.stream("GET", url, headers={
    "Authorization": f"Bearer {credentials.access_token}",
    "x-sfc-authorization": f"Bearer {credentials.sfc_token}",
}) as response:
    chunks = [chunk for chunk in response.iter_bytes()]
    return b"".join(chunks)
```

### 5.2 asn1crypto (CMS Unwrapping)

```python
from asn1crypto import cms

# ✅ Parse CMS ContentInfo envelope
content_info = cms.ContentInfo.load(raw_bytes)
signed_data = content_info['content']

# ✅ Extract encapsulated content (the Master List payload)
inner_bytes = signed_data['encap_content_info']['content'].parsed

# ✅ Extract certificates from SignedData.certificates SET
for cert_choice in signed_data['certificates']:
    cert_der = cert_choice.chosen.dump()

# ✅ Extract CRLs from SignedData.crls SET
for crl_choice in (signed_data['crls'] or []):
    crl_der = crl_choice.chosen.dump()
```

### 5.3 cryptography (X.509 Metadata)

```python
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

cert = x509.load_der_x509_certificate(der_bytes)

# ✅ Extract metadata
issuer = cert.issuer.rfc4514_string()
ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
x500_issuer = cert.issuer.public_bytes()  # raw DER encoding
serial = hex(cert.serial_number)
```

### 5.4 psycopg v3 (PostgreSQL)

```python
import psycopg

# ✅ Use connection context manager
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO root_ca (id, certificate, subject_key_identifier, ...) "
            "VALUES (%s, %s, %s, ...) ON CONFLICT (id) DO UPDATE SET ...",
            (record.id, record.certificate, record.subject_key_identifier, ...),
        )
    conn.commit()

# ✅ Wrap in Result at adapter boundary
def store(self, payload: MasterListPayload) -> Result[int]:
    return Result.from_computation(
        lambda: self._do_store(payload),
        ErrorCode.DATABASE_ERROR,
        "Failed to persist certificates",
    )
```

### 5.5 APScheduler (Scheduling)

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BlockingScheduler()
scheduler.add_job(
    run_pipeline,
    trigger=IntervalTrigger(hours=6),
    id="cert_parser_job",
    name="ICAO Master List sync",
    replace_existing=True,
)
scheduler.start()
```

### 5.6 tenacity (Retry/Backoff)

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

# ✅ Decorate the INNER method (the one that raises), NOT the Result-returning method
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,  # Let Result.from_computation catch the final exception
)
def _do_token_request(self) -> str:
    """OpenID Connect password grant with retry — exceptions caught by from_computation."""
    response = self._client.post(self._url, data=self._form_data)
    response.raise_for_status()
    return response.json()["access_token"]

# ✅ Public method wraps with Result — NO tenacity here
def acquire_token(self) -> Result[str]:
    return Result.from_computation(
        lambda: self._do_token_request(),
        ErrorCode.AUTHENTICATION_ERROR,
        "Access token acquisition failed",
    )
```

**Rules**:
- Only retry transient errors (network, timeout) — NEVER retry 401/403/validation
- Only apply to I/O adapter methods — NEVER retry pure computation (parsing)
- `reraise=True` so the final exception flows to `Result.from_computation()`

### 5.7 structlog (Observability)

```python
import structlog

log = structlog.get_logger()

# ✅ Structured context in every log line
log.info("pipeline.started", execution_id=exec_id, trigger="scheduled")
log.info("download.complete", size_bytes=len(data), duration_ms=elapsed)
log.warning("certificate.missing_ski", issuer=issuer, serial=serial)
log.error("store.failed", error_code="DATABASE_ERROR", detail=str(e))

# ✅ JSON output in production, colored console in development
# Configuration lives in main.py (composition root), not in adapters
```

**Rules**:
- Use structlog (not stdlib logging) for all application logging
- Log events as `module.action` format: `pipeline.started`, `download.complete`
- Always include structured context (key=value), never format strings
- Configure structlog ONCE in `main.py` — adapters just call `structlog.get_logger()`

---

## 6. Execution Context Pattern

Side effects (logging, timing, transactions) are SEPARATED from business logic:

```python
from railway import LoggingExecutionContext, Result

# ✅ Pure pipeline — no logging inside
def sync_pipeline(ports: Ports) -> Result[int]:
    return (
        ports.access_token_provider.acquire_token()
        .flat_map(lambda token: _build_credentials(token, ports.sfc_token_provider))
        .flat_map(ports.downloader.download)
        .flat_map(ports.parser.parse)
        .flat_map(ports.repository.store)
    )

# ✅ Execution context wraps the pipeline
ctx = LoggingExecutionContext(operation="MasterListSync")
result = ctx.execute(lambda: sync_pipeline(ports))
```

---

## 7. Testing Principles

### 7.1 Test Structure

```
tests/
├── unit/                    # Fast, no I/O, no database
│   ├── test_models.py       # Domain model validation
│   ├── test_pipeline.py     # Pipeline with mock ports
│   ├── test_cms_parser.py   # Parser with real ICAO fixture .bin files
│   └── test_http_client.py  # HTTP adapter with respx mocking
├── integration/             # Requires PostgreSQL (testcontainers)
│   └── test_repository.py   # Transactional replace, rollback, FK constraints
├── acceptance/              # Full pipeline, real ICAO data + real DB
│   └── test_pipeline_e2e.py # End-to-end with fixture .bin → parse → store → verify
└── fixtures/                # Real .bin/.der files extracted from ICAO PKD
    ├── ml_*.bin             # 24 Master List CMS blobs (2KB–957KB)
    ├── cert_*.der           # 5 individual DER certificates
    ├── corrupt.bin          # Invalid bytes for error-path testing
    ├── empty.bin            # Empty file for edge-case testing
    └── truncated.bin        # Truncated ASN.1 for error-path testing
```

### 7.2 TDD Workflow (NON-NEGOTIABLE)

All development follows **Test-Driven Development**:

```
  RED → GREEN → REFACTOR
  ───   ─────   ────────
  Write a failing test FIRST → Write minimal code to pass → Clean up
```

**Rules**:
1. **NEVER write production code without a failing test** — the test MUST exist and fail before implementation
2. **One test at a time** — write ONE test, make it pass, repeat
3. **Tests drive the design** — the test shapes the API, not the other way around
4. **Refactor only on GREEN** — never refactor while tests are failing

### 7.3 BDD Acceptance Tests (NON-NEGOTIABLE)

Acceptance tests describe **system behavior** using Given/When/Then structure:

```python
def test_parse_seychelles_master_list_extracts_single_certificate():
    """
    GIVEN a valid Seychelles Master List CMS blob (ml_sc.bin)
    WHEN the parser processes the binary
    THEN it returns a MasterListPayload with exactly 1 root CA certificate
    AND the certificate has a valid SKI and issuer containing 'SC' or 'Seychelles'
    """
    raw_bin = fixture_path("ml_sc.bin").read_bytes()
    result = parser.parse(raw_bin)
    payload = ResultAssertions.assert_success(result)
    assert len(payload.root_cas) >= 1
    assert any("SC" in (c.issuer or "") or "Seychelles" in (c.issuer or "") for c in payload.root_cas)
```

**Rules**:
1. **Every feature has acceptance tests** — written BEFORE or alongside unit tests
2. **Use Given/When/Then** in the docstring — this IS the specification
3. **Test real data** — acceptance tests use real ICAO fixtures, not synthetic mocks
4. **End-to-end** — acceptance tests exercise the full pipeline (mock HTTP → real parser → real DB)

### 7.4 Test Rules

1. **Unit tests use mock ports** — inject fake adapters that return predetermined `Result` values
2. **Use `ResultAssertions`** from the railway framework for all Result checks
3. **Test BOTH tracks** — success AND failure paths for every function
4. **Use `respx`** to mock httpx HTTP calls (never make real HTTP calls in unit tests)
5. **Use `pytest.mark.integration`** for tests requiring PostgreSQL (testcontainers)
6. **Use `pytest.mark.acceptance`** for full end-to-end tests with real fixtures + real DB
7. **Use real ICAO fixtures** in CMS parser unit tests — NOT synthetic mocks
8. **Test transactional rollback** in integration tests — verify old data preserved on failure

```python
from railway import ResultAssertions, ErrorCode

def test_parse_valid_bin():
    result = parser.parse(valid_bin_bytes)
    payload = ResultAssertions.assert_success(result)
    assert payload.total_certificates > 0

def test_parse_corrupt_bin():
    result = parser.parse(b"not-a-valid-cms")
    ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
    ResultAssertions.assert_failure_message_contains(result, "CMS")
```

---

## 8. Error Handling Contract

| Layer | Catches Exceptions? | Returns |
|-------|---------------------|---------|
| **Domain** (models, ports) | ❌ Never | `Result[T]` |
| **Pipeline** | ❌ Never | `Result[T]` via flat_map chain |
| **Adapters** | ✅ At boundary only | `Result[T]` via `Result.from_computation()` |
| **Main** | ✅ Last resort only | Logs and exits |

```python
# ✅ Adapter boundary — the ONLY place exceptions are caught
class HttpAccessTokenProvider:
    def acquire_token(self) -> Result[str]:
        return Result.from_computation(
            lambda: self._http_call(),
            ErrorCode.AUTHENTICATION_ERROR,
            "Access token acquisition failed",
        )

    def _http_call(self) -> str:
        """May raise — that's OK, from_computation catches it."""
        response = self._client.post(self._url, data=self._form_data)
        response.raise_for_status()
        return response.json()["access_token"]

class HttpSfcTokenProvider:
    def acquire_token(self, access_token: str) -> Result[str]:
        return Result.from_computation(
            lambda: self._do_login_request(access_token),
            ErrorCode.AUTHENTICATION_ERROR,
            "SFC token acquisition failed",
        )
```

---

## 9. File Creation Checklist

Before generating ANY file, verify:

- [ ] Module docstring present with layer identification
- [ ] `from __future__ import annotations` at top
- [ ] All functions return `Result[T]` if they can fail
- [ ] No `try/except` in domain or pipeline layers
- [ ] All data classes are `frozen=True, slots=True`
- [ ] All ports are `Protocol` with `@runtime_checkable`
- [ ] Type hints on every parameter and return value
- [ ] No mutable global state
- [ ] Follows the import direction: `main → pipeline → domain ← adapters`
- [ ] Code is immediately understandable without comments explaining "what"
- [ ] Functions do ONE thing and have self-documenting names
- [ ] No premature abstractions or "just in case" flexibility
- [ ] **Failing tests written BEFORE this code** (TDD red phase)
- [ ] **Unit tests cover both success and failure tracks**
- [ ] **BDD acceptance test exists for the feature** (Given/When/Then docstrings)

---

## 9.1 Simplicity & Readability Rules (NON-NEGOTIABLE)

1. **Choose the simplest solution** that correctly solves the problem
2. **Small functions** — each does ONE thing; if it needs a comment explaining what, rename or split
3. **Flat is better than nested** — prefer `flat_map` chains over deep callbacks
4. **Obvious data flow** — reader traces input → output without jumping between files
5. **No magic** — no hidden decorators, no metaclasses, no monkey-patching
6. **Minimize dependencies** — every dependency must justify its existence
7. **Self-documenting code** — variable and function names replace comments

---

## 9.2 Database — Transactional Replace Pattern

Each pipeline execution **completely replaces** all database data:

```python
# ✅ CORRECT — DELETE + INSERT in one ACID transaction
def _transactional_replace(self, payload: MasterListPayload) -> int:
    with psycopg.connect(self._dsn) as conn:
        with conn.transaction():  # ← ACID guarantee
            with conn.cursor() as cur:
                # Delete in FK-safe order (child → parent)
                cur.execute("DELETE FROM revoked_certificate_list")
                cur.execute("DELETE FROM crls")
                cur.execute("DELETE FROM dsc")
                cur.execute("DELETE FROM root_ca")
                # Insert new data
                rows = self._insert_all(cur, payload)
                return rows
        # If ANY exception → automatic rollback → old data preserved

# ❌ WRONG — DELETE outside transaction
def store(self, payload):
    conn.execute("DELETE FROM root_ca")  # COMMITTED!
    conn.execute("INSERT ...")            # If this fails, data is LOST
```

**Why**: PostgreSQL transactions are atomic. Either ALL changes commit or NONE do. The user's old data is always preserved if anything fails.

---

## 10. ICAO Master List — Technical Reference

### 10.1 Binary Format

The `.bin` file received from the REST service is a **CMS (PKCS#7) SignedData** structure (RFC 5652):

```
ContentInfo (OID: 1.2.840.113549.1.7.2 = signedData)
└── SignedData
    ├── version
    ├── digestAlgorithms
    ├── encapContentInfo          ← contains the Master List payload
    │   ├── eContentType (OID)
    │   └── eContent (OCTET STRING) ← the actual ML bytes
    ├── certificates [0] IMPLICIT  ← signing certificates (CSCA chain)
    ├── crls [1] IMPLICIT          ← optional CRLs
    └── signerInfos
```

### 10.2 Master List Inner Structure

The `eContent` inside the CMS envelope is an ASN.1 structure:

```
CscaMasterList ::= SEQUENCE {
    version    INTEGER,
    certList   SET OF Certificate
}
```

Each `Certificate` in `certList` is a standard X.509v3 DER-encoded certificate.

### 10.3 Extraction Pipeline

```
.bin (raw bytes)
  │
  ▼ asn1crypto: cms.ContentInfo.load()
ContentInfo
  │
  ▼ ['content'] → SignedData
  │
  ├── ['certificates']     → outer CSCA signing certs (DER)
  ├── ['crls']             → CRLs (DER)
  └── ['encap_content_info']['content'] → inner Master List bytes
       │
       ▼ asn1crypto: generic ASN.1 SEQUENCE parse
       CscaMasterList
         │
         └── certList → individual X.509 certificates (DER)
              │
              ▼ cryptography: x509.load_der_x509_certificate()
              Extract: SKI, AKI, issuer, serial, x500_issuer, etc.
```

---

## 11. Codebase Knowledge — Accumulated Findings

> These findings were accumulated during development (Phases 1–7 + hardening).
> They provide AI assistants with deep context that prevents repeating mistakes.

### 11.1 PEP 758 — Bare-Comma `except` (Python 3.14+)

This project uses PEP 758 bare-comma `except` syntax:

```python
# PEP 758 — catches BOTH exception types (NOT the old Py2 "except ExcA, name:" syntax)
except ExtensionNotFound, ValueError:
    return None
```

- **Verified**: Tested on Python 3.14.0 — `except A, B:` catches both `A` and `B` correctly.
- **Equivalent to**: `except (ExtensionNotFound, ValueError):`
- **CRITICAL**: Do NOT "fix" this to `except A as B:` — that would change semantics entirely.

### 11.2 Result API — Correct Usage

```python
# ✅ Correct — use .value() and .error()
result.value()   # raises ValueError if Failure
result.error()   # raises ValueError if Success

# ❌ Wrong — these do NOT exist
result.get_value()
result.get_failure()

# ✅ Test assertions
ResultAssertions.assert_success(result)
ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
```

### 11.3 Cognitive Complexity Rules

Each function should do ONE thing. Complexity thresholds:

- More than 2 levels of nesting → extract a helper
- More than 15 lines → consider splitting
- A boolean flag tracking state → extract the state transitions
- All functions must be ≤ CC 5

### 11.4 ICAO PKD Data Model

The ICAO Public Key Directory distributes **4 separate data types** via LDAP:

| Type | Format | LDIF Source |
|------|--------|-------------|
| **Master Lists** | CMS/PKCS#7 SignedData (OID `2.23.136.1.1.2`), per country | `icaopkd-002` → `pkdMasterListContent` |
| **DSCs** | Individual DER X.509 certificates (NOT CMS-wrapped) | `icaopkd-001` → `userCertificate;binary` |
| **CRLs** | Individual DER CRL objects (NOT CMS-wrapped) | `icaopkd-001` → `certificateRevocationList;binary` |
| **BCSCs** | Barcode Signer Certificates | Not in our LDIFs |

**Key insight**: The PKD does NOT serve a single bundled `.bin` containing ML+DSC+CRL.
Each is a separate LDAP entry. Our `ml_*.bin` fixtures ARE the exact format served by
the PKD for Master Lists. DSCs and CRLs are distributed as separate entries.

Public LDIF dumps: https://download.pkd.icao.int/
PKD participants connect via dedicated LDAP connections.
Non-participants download LDIF dumps.

### 11.5 Test Fixtures Inventory

```
tests/fixtures/
├── ml_*.bin           # 24 per-country Master List CMS blobs (2KB–957KB)
│                      # Extracted from icaopkd-002 LDIF → pkdMasterListContent
├── ml_composite.bin   # Synthetic composite: 3 countries (SC+BD+BW) + Colombia CRL
│                      # 5 inner CSCA certs + 3 outer signers + 1 CRL (15 revoked)
│                      # Exercises ALL parser code paths
├── cert_*.der         # 5 individual DER certificates from icaopkd-001
├── crl_sample.der     # Real Colombia CRL (967 bytes, 15 revoked entries)
├── corrupt.bin        # Invalid random bytes
├── empty.bin          # Zero-length file
└── truncated.bin      # Valid ASN.1 header, truncated payload
```

The composite fixture (`ml_composite.bin`) is built by `scripts/build_composite_fixture.py`
and is the ONLY fixture that exercises the CRL extraction code paths.

### 11.6 Coverage Profile

| File | Coverage | Notes |
|------|:--------:|-------|
| `cms_parser.py` | 96% | Remaining: AKI `key_identifier is None` branch, `certs_set is None` |
| `http_client.py` | 100% | Complete |
| `repository.py` | 100% | Complete |
| `pipeline.py` | 100% | Complete |
| `models.py` | 100% | Complete |
| `ports.py` | 100% | Complete |
| `config.py` | 100% | Complete |
| `scheduler.py` | 88% | Signal handler body untestable (sends `sys.exit(0)`) |
| `main.py` | 40% | Composition root — untestable by design |

**Total**: 91% (117 tests). The 9% gap is entirely in `main.py` (composition root)
and signal handlers — both are infrastructure code untestable without real processes.

### 11.7 Known Bug Fix: `_extract_country_from_issuer`

A latent bug was discovered during complexity refactoring — the function had
double-nested iteration (`for attr in issuer: for name_attr in attr:`) that assumed
`x509.Name` yields containers, but `cryptography` library `x509.Name` yields
`NameAttribute` objects directly. Fixed to single-loop iteration. This bug was never
triggered because no ICAO ML fixture contained CRLs until the composite fixture was built.

### 11.8 Deprecation Fix: `revocation_date_utc`

The `cryptography` library deprecated `revoked_cert.revocation_date` (naive datetime).
We use `revoked_cert.revocation_date_utc` (timezone-aware) instead. The
`RevokedCertificateRecord.revocation_date` field type (`datetime | None`) accepts both.

### 11.9 Quality Gate

| Check | Status | Command |
|-------|:------:|---------|
| Tests | ✅ 111 passed | `pytest -v --tb=short` (unit only) |
| Type Safety | ✅ 0 errors | `mypy src/ --strict` |
| Linting | ✅ 0 errors | `ruff check src/ tests/ scripts/` |
| Coverage | ✅ 91% | `pytest --cov=cert_parser` |
| Cognitive Complexity | ✅ All functions ≤ CC 5 | Manual audit |

### 11.10 Dagger Go CI/CD Pipeline — Architecture & Rules

The project includes a **Dagger Go SDK** pipeline (`dagger_go/`) that automates
the full CI/CD lifecycle: clone → test → lint → type-check → Docker build → publish to GHCR.

#### Pipeline Structure

```
dagger_go/
├── main.go              # Primary pipeline (7 configurable stages)
├── main_test.go         # 12 Go unit tests for pipeline logic
├── corporate_main.go    # Corporate variant (MITM proxy/custom CA support)
├── go.mod / go.sum      # Go 1.24, Dagger SDK v0.19.7
├── run.sh               # Run pipeline (auto-loads credentials/.env)
├── run-corporate.sh     # Run corporate pipeline (-tags corporate)
├── test.sh              # Build + test Go pipeline locally
└── credentials/         # .env with CR_PAT/USERNAME — .gitignored, NEVER committed
```

#### Pipeline Stages (7 total, all individually configurable)

| # | Stage | Location | Env Var | Default |
|---|-------|----------|---------|---------|
| 1 | Unit Tests | Dagger container | `RUN_UNIT_TESTS` | `true` |
| 2 | Integration Tests | **Host machine** | `RUN_INTEGRATION_TESTS` | `true` |
| 3 | Acceptance Tests | **Host machine** | `RUN_ACCEPTANCE_TESTS` | `true` |
| 4 | Lint (ruff) | Dagger container | `RUN_LINT` | `true` |
| 5 | Type Check (mypy) | Dagger container | `RUN_TYPE_CHECK` | `true` |
| 6 | Docker Build | Dagger | always | — |
| 7 | Publish to GHCR | Dagger | always | — |

Example usage: `RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh`

#### Key Design Decisions

1. **Project name auto-discovery**: The pipeline extracts `name = "..."` from `pyproject.toml`
   via regex — no hardcoded project names. Falls back to `REPO_NAME` env var if parsing fails.

2. **Local framework install order**: `python_framework/` MUST be installed before the main
   project (`pip install -e ./python_framework` then `pip install -e .[dev,server]`),
   because `cert-parser` depends on `railway-rop` which lives locally in the monorepo.

3. **Image tagging**: `v0.1.0-<sha7>-<YYYYMMDD-HHMM>` for versioned, plus `:latest`.
   Published to `ghcr.io/<username>/<image-name>`.

4. **Credentials**: Stored in `dagger_go/credentials/.env` (gitignored). Required vars:
   `CR_PAT` (GitHub PAT with `write:packages`), `USERNAME` (GitHub username).
   `run.sh` auto-loads this file via `source credentials/.env`.

### 11.11 Testcontainers in Dagger — Docker-in-Docker Limitation

**CRITICAL FINDING**: Testcontainers (Python `testcontainers[postgres]`) **cannot run
inside Dagger containers**. Dagger containers use Docker-in-Docker, and testcontainers
needs to bind-mount volumes and access the Docker socket natively. Inside Dagger, the
Docker socket paths get remapped, causing volume mount mismatches that break
testcontainers' container lifecycle management.

**Solution**: Integration and acceptance tests (which use testcontainers to spin up
PostgreSQL) run on the **host machine** via `exec.Command`, NOT inside the Dagger
container. The pipeline:

1. Auto-detects the Docker socket via `getDockerSocketPath()` (platform-aware:
   Linux `/var/run/docker.sock`, macOS `~/.docker/run/docker.sock` or Colima,
   Windows named pipe).
2. If Docker is unavailable, those stages are **skipped** with a warning — not failed.
3. Host test execution uses `runTestsOnHost()` which:
   - Discovers the project root (parent of `dagger_go/`)
   - Prefers `.venv/bin/pytest`, falls back to system `pytest`
   - Runs `pytest -v --tb=short -m <marker>` where marker is `integration` or `acceptance`
   - Streams output to stdout in real-time while buffering for summary parsing
   - Parses the pytest summary line (`X passed, Y failed`) for a formatted report

**Rule**: NEVER attempt to run testcontainers-based tests inside a Dagger container.
Always use `exec.Command` for host-based execution of any test that requires Docker.

### 11.12 Go `vet` — Non-Constant Format Strings

Go's `vet` tool (run automatically by `go test`) flags `fmt.Printf` calls where the
format string is not a compile-time constant:

```go
// ❌ Fails go vet — non-constant format string
fmt.Printf("\n" + strings.Repeat("=", 80) + "\n")

// ✅ Correct — use %s placeholder
fmt.Printf("\n%s\n", strings.Repeat("=", 80))
```

**Rule**: ALL `fmt.Printf` calls MUST use constant format strings with `%` placeholders.
Concatenated or computed format strings will fail `go vet` and therefore `go test`.

### 11.13 Go Deprecated APIs — `strings.Title`

`strings.Title` is deprecated since Go 1.18. The recommended replacement is
`golang.org/x/text/cases`, but for simple single-word capitalization, a manual
approach avoids the extra dependency:

```go
// ❌ Deprecated — triggers staticcheck warning
strings.Title(marker)

// ✅ Simple capitalization without extra dependencies
strings.ToUpper(marker[:1]) + marker[1:]
```

### 11.14 Go Build Tags — Corporate Pipeline Isolation

The `corporate_main.go` file contains a full alternative pipeline with MITM proxy
and custom CA support. To prevent a "multiple main functions" build error, it uses
a Go build constraint:

```go
//go:build corporate
```

**Rules**:
- Default `go build` compiles ONLY `main.go` (the standard pipeline)
- Corporate build: `go build -tags corporate -o railway-corporate-dagger-go corporate_main.go`
- The build tag MUST be on the very first line of the file (before `package main`)
- `run-corporate.sh` handles the `-tags corporate` flag automatically

### 11.15 Dagger Pipeline Go Quality Gate

| Check | Status | Command |
|-------|:------:|---------|
| Build | ✅ 0 errors | `go build -o /dev/null .` |
| Tests | ✅ 12 passed | `go test -v -run Test` |
| Vet | ✅ 0 warnings | `go vet ./...` (runs automatically with `go test`) |

Tests cover: Pipeline struct configuration, configurable flags (default values + explicit),
`parseEnvBool` (12 value variants + defaults), `extractProjectName` (found + missing),
`dockerSafeName` (3 transformation cases), `getDockerSocketPath` (platform detection),
image naming, Git URL construction, environment variables.

### 11.16 Shell Script Conventions — `run.sh` / `test.sh`

Both `run.sh` and `test.sh` follow these conventions:

1. **Auto-discovery**: `REPO_NAME` is auto-discovered from the parent directory name
   (`basename "$(cd .. && pwd)"`) — no hardcoded project names.
2. **Credential loading**: `run.sh` sources `credentials/.env` if present (`set -a; source; set +a`).
3. **Binary caching**: `run.sh` builds the Go binary only if `./railway-dagger-go` doesn't exist.
4. **Fail-fast**: Both use `set -e` — any command failure aborts the script immediately.
5. **Go prerequisite check**: `test.sh` verifies Go is installed before proceeding.

### 11.17 REST Trigger Endpoint & db_migrations

**POST /trigger**: The ASGI app exposes a `POST /trigger` endpoint for manual pipeline
execution via tools like Postman. It runs the full pipeline (auth → download → parse → store)
and returns JSON with `rows_stored` on success or error details on failure. Uses
`asyncio.to_thread` to avoid blocking the ASGI event loop.

**db_migrations/**: Contains reference-only SQL files documenting the expected PostgreSQL
schema. These are NOT auto-applied migrations. The `db_migrations/README.md` explains
this clearly. Any schema changes must be reflected in both the SQL files and the
repository's INSERT statements.

### 11.18 master_list_issuer — CMS Signer Tracking

The `root_ca` table has a `master_list_issuer` column (not present in `dsc`) that
tracks which entity signed the CMS Master List envelope. This is extracted via:
1. SignerInfo `issuerAndSerialNumber` → signer's issuer name (preferred)
2. First outer certificate's subject → fallback when SID type is `subjectKeyIdentifier`

Some ICAO Master Lists use `issuerAndSerialNumber` (e.g., Seychelles) while others
use `subjectKeyIdentifier` (e.g., France). The composite fixture has no signer infos
and falls back to outer certificate subject. The repository uses separate INSERT
statements for `root_ca` (10 columns including `master_list_issuer`) and `dsc` (9 columns).

---

## 12. Database Schema Reference

> **Note**: The SQL files in `db_migrations/` are reference-only documentation.
> They are NOT applied automatically. See `db_migrations/README.md` for details.

```sql
-- Root CA certificates (CSCA)
CREATE TABLE root_ca (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    master_list_issuer        TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

-- Document Signer Certificates (DSC) — NOT same schema as root_ca (no master_list_issuer)
CREATE TABLE dsc (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

-- Certificate Revocation Lists
CREATE TABLE crls (
    id          UUID PRIMARY KEY,
    crl         BYTEA NOT NULL,
    source      TEXT,
    issuer      TEXT,
    country     TEXT,
    updated_at  TIMESTAMP WITHOUT TIME ZONE
);

-- Individual revoked certificate entries
CREATE TABLE revoked_certificate_list (
    id                UUID PRIMARY KEY,
    source            TEXT,
    country           TEXT,
    isn               TEXT,
    crl               UUID,       -- FK to crls.id
    revocation_reason TEXT,
    revocation_date   TIMESTAMP WITHOUT TIME ZONE,
    updated_at        TIMESTAMP WITHOUT TIME ZONE
);
```
