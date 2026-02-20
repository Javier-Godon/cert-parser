# Testing Strategy

## Test Pyramid

```
        ╱╲
       ╱  ╲        Acceptance (E2E)
      ╱ 5  ╲       Real fixtures + real DB → full pipeline
     ╱──────╲
    ╱        ╲      Integration
   ╱   15    ╲     Real PostgreSQL (testcontainers)
  ╱────────────╲
 ╱              ╲    Unit
╱      89       ╲   Mock ports, no I/O
╱────────────────╲
```

**Total: 109 tests** — 91% code coverage.

## Test Layer Details

### Unit Tests (`tests/unit/`)

**What they test**: Business logic in isolation. No I/O, no database, no HTTP.

| File | Tests | What |
|------|:-----:|------|
| `test_models.py` | Domain model creation, immutability, defaults |
| `test_pipeline.py` | Pipeline with mock ports — success and failure paths |
| `test_cms_parser.py` | CMS parser with **real ICAO fixture** `.bin` files |
| `test_http_client.py` | HTTP adapters with `respx` mocking |
| `test_config.py` | Configuration validation |
| `test_scheduler.py` | Scheduler creation and job registration |

**Key rule for CMS parser tests**: Use **real ICAO fixtures**, not synthetic mocks. The `.bin` files in `tests/fixtures/` are actual Master Lists from the ICAO PKD.

### Integration Tests (`tests/integration/`)

**What they test**: Database interactions with a real PostgreSQL instance.

**Infrastructure**: `testcontainers` spins up `postgres:16-alpine` in Docker for each test session.

**Setup**:
1. Session fixture creates PostgreSQL container + creates schema (DDL)
2. Per-test fixture truncates all tables before each test

```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        # Create schema
        yield pg

@pytest.fixture()
def dsn(postgres_container):
    # Truncate all tables before each test
    return connection_url
```

**What they verify**:
- Store + retrieve — data persists correctly
- Transactional replace — old data is removed, new data is inserted
- FK constraints — revoked entries link to CRLs
- Rollback preservation — on failure, old data remains
- Empty payload handling

### Acceptance Tests (`tests/acceptance/`)

**What they test**: Full pipeline from parsing through persistence.

**Structure**: `GIVEN / WHEN / THEN` (BDD style) in docstrings.

```python
def test_parse_seychelles_master_list_extracts_single_certificate():
    """
    GIVEN a valid Seychelles Master List CMS blob (ml_sc.bin)
    WHEN the parser processes the binary
    THEN returns a MasterListPayload with exactly 1 root CA certificate
    AND the certificate has a valid SKI and issuer containing 'SC'
    """
```

**Data flow**: Real `.bin` fixture → CMS parser → MasterListPayload → PostgreSQL → SELECT to verify.

## Test Fixtures

```
tests/fixtures/
├── ml_*.bin           # 24 per-country Master List CMS blobs (2KB–957KB)
│                      # Extracted from ICAO PKD LDIF (icaopkd-002)
├── ml_composite.bin   # Synthetic composite: SC+BD+BW certs + Colombia CRL
│                      # 5 inner + 3 outer certs + 1 CRL (15 revoked entries)
│                      # ONLY fixture that exercises CRL code paths
├── cert_*.der         # 5 individual DER certificates (from icaopkd-001)
├── crl_sample.der     # Real Colombia CRL (967 bytes, 15 revoked entries)
├── corrupt.bin        # Random invalid bytes (error path testing)
├── empty.bin          # Zero-length file (edge case)
└── truncated.bin      # Valid ASN.1 header + truncated payload (edge case)
```

### The Composite Fixture

`ml_composite.bin` is special — it's built by `scripts/build_composite_fixture.py` and is the ONLY fixture that contains CRLs. Without it, the CRL extraction code paths would go untested.

Contents:
- **3 countries** of inner certificates: Seychelles, Bangladesh, Botswana (5 total)
- **3 outer signing certificates** (from the CMS envelope)
- **1 CRL** from Colombia with 15 revoked certificate entries

## TDD Workflow

All development follows **Test-Driven Development**:

```
RED → GREEN → REFACTOR
```

1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to make it pass
3. **REFACTOR**: Clean up while tests are green

### Practical Example

```python
# 1. RED — write failing test
def test_parse_corrupt_bin():
    result = parser.parse(b"not-a-valid-cms")
    ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
    ResultAssertions.assert_failure_message_contains(result, "CMS")

# 2. GREEN — implement parse() with error handling
# 3. REFACTOR — extract helper functions, improve names
```

## Result Assertion Helpers

The railway framework provides purpose-built assertion helpers:

```python
from railway import ResultAssertions, ErrorCode

# Assert success and extract value (fails test if Result is Failure)
payload = ResultAssertions.assert_success(result)
assert payload.total_certificates > 0

# Assert failure with specific error code
ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)

# Assert failure message contains text
ResultAssertions.assert_failure_message_contains(result, "CMS")
```

## Testing Both Tracks

Every function must have tests for both success AND failure paths:

```python
# ✅ Success track
def test_parse_valid_bin():
    result = parser.parse(valid_bin_bytes)
    payload = ResultAssertions.assert_success(result)
    assert payload.total_certificates > 0

# ✅ Failure track
def test_parse_corrupt_bin():
    result = parser.parse(b"not-valid")
    ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
```

## Mock Ports Pattern

Pipeline tests inject mock ports:

```python
class MockAccessTokenProvider:
    def acquire_token(self) -> Result[str]:
        return Result.success("fake-access-token")

class MockSfcTokenProvider:
    def acquire_token(self, access_token: str) -> Result[str]:
        return Result.success("fake-sfc-token")

class MockFailingParser:
    def parse(self, raw_bin: bytes) -> Result[MasterListPayload]:
        return Result.failure(ErrorCode.TECHNICAL_ERROR, "parse failed")

def test_pipeline_success():
    result = run_pipeline(
        access_token_provider=MockAccessTokenProvider(),
        sfc_token_provider=MockSfcTokenProvider(),
        downloader=MockDownloader(),
        parser=MockParser(),
        repository=MockRepository(),
    )
    ResultAssertions.assert_success(result)

def test_pipeline_parser_failure():
    result = run_pipeline(
        access_token_provider=MockAccessTokenProvider(),
        sfc_token_provider=MockSfcTokenProvider(),
        downloader=MockDownloader(),
        parser=MockFailingParser(),  # ← fails here
        repository=MockRepository(), # ← never called
    )
    ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)
```

## HTTP Mocking with respx

```python
import respx
from httpx import Response

@respx.mock
def test_download_success(respx_mock):
    respx_mock.get("https://example.com/download").respond(
        content=b"\x30\x82...",  # fake binary
        status_code=200,
    )
    credentials = AuthCredentials(access_token="fake-access", sfc_token="fake-sfc")
    result = downloader.download(credentials)
    data = ResultAssertions.assert_success(result)
    assert data == b"\x30\x82..."

@respx.mock
def test_download_404(respx_mock):
    respx_mock.get("https://example.com/download").respond(status_code=404)
    credentials = AuthCredentials(access_token="fake-access", sfc_token="fake-sfc")
    result = downloader.download(credentials)
    ResultAssertions.assert_failure(result, ErrorCode.EXTERNAL_SERVICE_ERROR)
```

## Test Markers

```python
@pytest.mark.integration    # Requires Docker + PostgreSQL
@pytest.mark.acceptance     # Full E2E with fixtures + DB
```

Run specific layers:
```bash
pytest tests/unit/                    # Unit only (fast, no Docker)
pytest tests/integration/ -m integration  # Integration only
pytest tests/acceptance/ -m acceptance    # Acceptance only
pytest                                # Everything
```

## Coverage Profile

| Module | Coverage | Notes |
|--------|:--------:|-------|
| `cms_parser.py` | 96% | Remaining: AKI `key_identifier is None` branch |
| `http_client.py` | 100% | — |
| `repository.py` | 100% | — |
| `pipeline.py` | 100% | — |
| `models.py` | 100% | — |
| `ports.py` | 100% | — |
| `config.py` | 100% | — |
| `scheduler.py` | 88% | Signal handler body untestable |
| `main.py` | 40% | Composition root — untestable by design |

**Total: 91%** — the gap is `main.py` (composition root wiring) and signal handlers.

## Quality Gate

```bash
# All must pass before merge
pytest -v --tb=short           # 109 tests pass
mypy src/ --strict             # 0 type errors
ruff check src/ tests/ scripts/  # 0 lint errors
pytest --cov=cert_parser       # ≥91% coverage
```
