# Libraries & Tooling — Rationale and Usage

## Why Two Libraries for Parsing?

cert-parser uses **two** libraries for certificate work:

| Library | Role | Why |
|---------|------|-----|
| **asn1crypto** | CMS/PKCS#7 envelope unwrapping | The ONLY Python library that exposes `eContent`, `certificates`, and `crls` from `SignedData` |
| **cryptography** (PyCA) | X.509 metadata extraction | Best-in-class typed API for certificate fields (SKI, AKI, issuer, serial) |

### Why not just `cryptography`?

`cryptography` can parse X.509 certificates and CRLs, and can verify CMS signatures. But it **cannot** give you access to:
- The `certificates` field of a `SignedData` structure (the outer signing certs)
- The `crls` field (revocation lists embedded in the CMS)
- The `eContent` payload (the Master List bytes)

`cryptography` treats CMS as an opaque blob for signature verification — it doesn't expose the internal structure.

### Why not just `asn1crypto`?

`asn1crypto` can parse the CMS envelope beautifully and even has X.509 certificate classes. However:
- Its certificate metadata extraction is less refined than `cryptography`'s
- `cryptography` has typed Python classes for every extension (e.g., `SubjectKeyIdentifier`, `AuthorityKeyIdentifier`)
- `cryptography` properly handles edge cases in extension parsing

### The Division of Labor

```
asn1crypto                           cryptography
────────────────────────────         ────────────────────────────
CMS ContentInfo → SignedData         DER bytes → x509.Certificate
SignedData → certificates            cert.issuer.rfc4514_string()
SignedData → eContent (ML bytes)     cert.extensions (SKI, AKI)
SignedData → crls                    x509.load_der_x509_crl()
CscaMasterList → certList            CRL → revoked entries
```

---

## asn1crypto (1.5.1)

### What It Does

Parses ASN.1/DER binary structures. Used exclusively for CMS envelope operations.

### Custom ASN.1 Classes

cert-parser defines two custom classes for the ICAO Master List schema:

```python
from asn1crypto import core
from asn1crypto import x509 as asn1_x509

class _CertificateSet(core.SetOf):
    _child_spec = asn1_x509.Certificate

class _CscaMasterList(core.Sequence):
    _fields = [
        ("version", core.Integer),
        ("cert_list", _CertificateSet),
    ]
```

These map directly to the ICAO ASN.1 specification:
```
CscaMasterList ::= SEQUENCE {
    version    INTEGER,
    certList   SET OF Certificate
}
```

### Usage Patterns

```python
# Load CMS envelope
content_info = cms.ContentInfo.load(raw_bytes)
signed_data = content_info['content']

# Access fields using dictionary-style syntax
certs = signed_data['certificates']     # CertificateSet or None
crls = signed_data['crls']             # RevocationInfoChoices or None
econtent = signed_data['encap_content_info']['content']

# Serialize back to DER
der_bytes = cert_choice.chosen.dump()

# Parse custom structure
ml = _CscaMasterList.load(inner_bytes)
cert_list = ml['cert_list']
```

### Key Concepts

- **`.load(bytes)`**: Deserialize DER bytes into typed ASN.1 objects
- **`['field_name']`**: Access fields by name (from `_fields` definition)
- **`.chosen`**: Resolve ASN.1 CHOICE types (returns the actual inner type)
- **`.dump()`**: Serialize back to DER bytes
- **`.native`**: Get the Python-native representation (bytes, int, str, etc.)
- **`SetOf` / `Sequence`**: Collection types — iterate with `for item in collection`

---

## cryptography / PyCA (46.0.5)

### What It Does

Parses X.509 certificates and CRLs. Provides typed Python objects for all fields and extensions.

### Certificate Metadata Extraction

```python
from cryptography import x509

cert = x509.load_der_x509_certificate(der_bytes)

# Basic fields
cert.issuer                    # x509.Name object
cert.issuer.rfc4514_string()   # "C=DE,O=bsi,CN=csca-germany"
cert.issuer.public_bytes()     # DER-encoded X.500 Name (raw bytes)
cert.serial_number             # int
hex(cert.serial_number)        # "0x1a2b3c..."

# Extensions
cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
# → Extension(value=SubjectKeyIdentifier(digest=b'\x...'))
# → .value.digest.hex() → "a1b2c3..."

cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
# → Extension(value=AuthorityKeyIdentifier(key_identifier=b'\x...'))
# → .value.key_identifier.hex() → "d4e5f6..."
```

### CRL Parsing

```python
crl = x509.load_der_x509_crl(crl_der)

crl.issuer.rfc4514_string()    # CRL issuer
len(list(crl))                 # number of revoked entries

for revoked in crl:
    revoked.serial_number                    # int
    revoked.revocation_date_utc              # datetime (timezone-aware)
    revoked.extensions.get_extension_for_class(x509.CRLReason)
    # → Extension(value=CRLReason(reason=ReasonFlags.key_compromise))
```

### Important: `revocation_date_utc` vs `revocation_date`

The `cryptography` library **deprecated** `revoked_cert.revocation_date` (returns naive datetime). Always use `revoked_cert.revocation_date_utc` (returns timezone-aware datetime):

```python
# ✅ Correct — timezone-aware
date = revoked_cert.revocation_date_utc

# ❌ Deprecated — will emit warnings
date = revoked_cert.revocation_date
```

### Exception Handling

`cryptography` raises `ExtensionNotFound` when a certificate doesn't have a requested extension. cert-parser handles this with PEP 758 bare-comma syntax:

```python
try:
    ext = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    return ext.value.digest.hex()
except ExtensionNotFound, ValueError:  # PEP 758 — catches BOTH
    return None
```

---

## httpx (0.28.1)

### What It Does

Sync HTTP client for REST API calls. Used for token acquisition and binary download.

### Why httpx Over requests?

- Modern, actively maintained
- First-class streaming support
- Built-in timeout support (per-request, not global)
- Mockable with `respx` library (purpose-built for httpx)
- Consistent sync/async API (we use sync)

### Usage Patterns

```python
with httpx.Client(timeout=60) as client:
    # Step 1: Access token acquisition (OpenID Connect password grant)
    response = client.post(url, data={
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
    })
    response.raise_for_status()
    access_token = response.json()["access_token"]

    # Step 2: SFC login with access token
    response = client.post(login_url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"borderPostId": 1, "boxId": 1, "passengerControlType": 1},
    )
    response.raise_for_status()
    sfc_token = response.text

    # Step 3: Binary download with dual-token auth
    response = client.get(download_url, headers={
        "Authorization": f"Bearer {access_token}",
        "x-sfc-authorization": f"Bearer {sfc_token}",
    })
    response.raise_for_status()
    data = response.content  # bytes
```

### Key Design Choices

- **Context manager** (`with httpx.Client() as client:`) — ensures connection cleanup
- **`.raise_for_status()`** — converts 4xx/5xx to exceptions (caught by `from_computation`)
- **New client per request** — no connection pooling needed for infrequent (<= hourly) calls

---

## tenacity (9.1.4)

### What It Does

Retry decorator with configurable backoff strategies. Applied to the inner (exception-raising) HTTP methods only.

### Configuration

```python
@retry(
    stop=stop_after_attempt(3),           # Max 3 attempts
    wait=wait_exponential(               # Exponential backoff
        multiplier=1,
        min=0.1,                         # First retry after 0.1s
        max=30,                          # Cap at 30s
    ),
    retry=retry_if_exception_type((      # Only retry transient errors
        httpx.TimeoutException,
        httpx.NetworkError,
    )),
    reraise=True,                        # Let final exception propagate
)
def _do_token_request(self) -> str:
    ...
```

### Critical Rules

1. **Decorate the INNER method** (the one that raises), NOT the Result-returning public method
2. **Only retry transient errors** — network timeouts, connection refused. NEVER retry 401/403/validation
3. **`reraise=True`** so the final exception flows to `Result.from_computation()`
4. **Never retry pure computation** — parsing failures are deterministic, retrying is pointless

### Retry Flow

```
Attempt 1 → TimeoutException → wait 0.1s
Attempt 2 → TimeoutException → wait 0.2s
Attempt 3 → TimeoutException → reraise → Result.from_computation catches it
                                        → Result.failure(AUTHENTICATION_ERROR, ...)
```

---

## psycopg (3.3.2)

### What It Does

PostgreSQL driver (v3). Used for transactional replace operations.

### Why psycopg v3 Over v2?

- Modern Python 3.x design (async-first, context managers)
- `conn.transaction()` context manager for ACID guarantees
- Parameterized queries with `%s` (safe from SQL injection)
- Type-aware parameter binding (UUID, bytes, datetime handled natively)

### Usage Pattern

```python
with psycopg.connect(dsn) as conn, conn.transaction(), conn.cursor() as cur:
    # Everything inside this block is one ACID transaction
    cur.execute("DELETE FROM revoked_certificate_list")
    cur.execute("DELETE FROM crls")
    cur.execute("DELETE FROM dsc")
    cur.execute("DELETE FROM root_ca")
    cur.execute("INSERT INTO root_ca (...) VALUES (%s, %s, ...)", (id, cert, ...))
    # If ANY exception occurs here → automatic rollback → old data preserved
# COMMIT happens automatically when context manager exits cleanly
```

### Key Features Used

- **Triple context manager**: `psycopg.connect()` + `conn.transaction()` + `conn.cursor()`
- **Parameterized queries**: `%s` placeholders — never string formatting
- **Automatic rollback**: If an exception exits the `transaction()` block, all changes are rolled back
- **Native type support**: `UUID`, `bytes`, `datetime`, `None` all bind correctly

---

## APScheduler (3.11.2)

### What It Does

Lightweight in-process scheduler. Runs the pipeline at configurable intervals.

### Configuration

```python
scheduler = BlockingScheduler()
scheduler.add_job(
    _job,
    trigger=IntervalTrigger(hours=interval_hours),
    id="cert_parser_sync",
    name="ICAO Master List sync",
    replace_existing=True,
)
```

### Why BlockingScheduler?

This application has a single purpose: run the pipeline periodically. There's no web server or other concurrent work. `BlockingScheduler` blocks the main thread and manages the timing loop — the simplest possible approach.

### Signal Handling

```python
signal.signal(signal.SIGINT, _shutdown)   # Ctrl+C
signal.signal(signal.SIGTERM, _shutdown)  # Docker stop, kill

def _shutdown(signum, frame):
    scheduler.shutdown(wait=False)
    sys.exit(0)
```

---

## pydantic-settings (2.13.0)

### What It Does

Typed, validated configuration from environment variables and `.env` files.

### Sub-Settings Pattern

```python
class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    url: str
    client_id: str
    client_secret: SecretStr    # Masked in logs

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auth: AuthSettings = Field(default_factory=AuthSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
```

### Key Features

- **`SecretStr`** for `client_secret` and `dsn` — never accidentally logged
- **`env_prefix`** — `AUTH_URL`, `AUTH_CLIENT_ID`, etc.
- **Validation at startup** — missing env vars fail immediately, not at runtime
- **Type coercion** — `SCHEDULER_INTERVAL_HOURS=6` → `int(6)` automatically

---

## structlog (25.5.0)

### What It Does

Structured logging library. All log lines include key=value context.

### Configuration (in `main.py`)

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### Usage Pattern

```python
log = structlog.get_logger()
log.info("parser.complete", inner_certs=5, outer_certs=3, total_root_cas=8)
log.warning("certificate.missing_ski", issuer=issuer_str, serial=serial_hex)
log.error("store.failed", error_code="DATABASE_ERROR", detail=str(e))
```

### Rules

- Event names follow `module.action` format
- Always structured context (key=value), never format strings
- Configure ONCE in `main.py`, use `get_logger()` everywhere else
- `ConsoleRenderer` for development, swap to `JSONRenderer` for production

---

## Testing Libraries

### pytest (8.x)

Standard test runner. Custom markers for test layers:
- `@pytest.mark.integration` — requires PostgreSQL (testcontainers)
- `@pytest.mark.acceptance` — full end-to-end with real fixtures + real DB

### respx (0.22.0)

Purpose-built mock library for httpx:

```python
@respx.mock
def test_token_acquisition(respx_mock):
    respx_mock.post("https://auth.example.com/token").respond(
        json={"access_token": "test-token"}
    )
    result = provider.acquire_token()
    assert result.is_success()
```

### testcontainers (4.14.1)

Spins up real PostgreSQL in Docker for integration tests:

```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        # Create schema, yield container
        yield pg
```

### mypy (strict mode)

Static type checking. All function signatures must have type hints. No `Any` unless truly unavoidable. Run with `mypy src/ --strict`.

### ruff

Linting and formatting. Line length 100. Run with `ruff check src/ tests/ scripts/` and `ruff format src/ tests/ scripts/`.
