# Railway-Oriented Programming Framework (`python_framework/`)

> **Quick navigation**: If you just want the API reference, go directly to
> [`python_framework/README.md`](../../python_framework/README.md).
>
> This document explains **how the framework fits into cert-parser** and the design
> decisions behind using it here.

---

## What Is This Framework?

`python_framework/` is a **local Python package** named `railway-rop` that lives inside
the cert-parser monorepo. It implements the **Railway-Oriented Programming (ROP)** pattern
— a functional approach to error handling that replaces exceptions with explicit `Result[T]`
values.

It is NOT a third-party package. It is part of this project and installed via:

```bash
pip install -e "./python_framework"   # installs as 'railway-rop'
```

---

## Why a Local Framework?

For a security-critical PKI application, the design mandates:
- **No hidden exceptions** — every failure is visible in function signatures
- **Explicit error codes** — `AUTHENTICATION_ERROR`, `DATABASE_ERROR`, `TECHNICAL_ERROR` etc.
- **Composable pipelines** — operations chained with `flat_map` without nested try/catch

No existing library on PyPI fits this exactly:
- `returns` (dry-python) — heavy, academic, designed for Haskell-style FP
- `result` (rustedpy) — minimal, no error codes, no HTTP mapping, no execution context
- Neither supports the structured `ErrorCode` enum we use for HTTP status mapping

Building it locally also means we OWN it: no supply-chain risk, no API changes from a
third party breaking the codebase.

---

## Package Structure

```
python_framework/
├── pyproject.toml              ← package config (name: railway-rop, version: 1.0.0)
├── README.md                   ← complete API reference (read this!)
├── src/
│   └── railway/
│       ├── __init__.py         ← public API exports (Result, ErrorCode, etc.)
│       ├── result.py           ← Result[T] monad (Success | Failure, 350 lines)
│       ├── failure.py          ← ErrorCode enum + FailureDescription
│       ├── execution.py        ← ExecutionContext protocol + implementations
│       ├── result_failures.py  ← Convenience failure factories
│       ├── assertions.py       ← Test assertion helpers (ResultAssertions)
│       └── http_support.py     ← HTTP status mapping + FastAPI/Flask response builders
├── tests/
│   ├── test_result.py          ← 50+ tests for Result monad
│   ├── test_failure.py
│   ├── test_execution.py
│   ├── test_result_failures.py
│   ├── test_assertions.py
│   └── test_http_support.py
└── examples/
    ├── create_order.py         ← Handler→Data/Ports→Stages full example
    ├── fastapi_integration.py  ← FastAPI controller pattern
    └── value_objects.py        ← Self-validating domain objects
```

---

## How cert-parser Uses It

### 1. Every adapter returns `Result[T]`

```python
# src/cert_parser/adapters/http_client.py
from railway.result import Result
from railway import ErrorCode

class HttpAccessTokenProvider:
    def acquire_token(self) -> Result[str]:
        return Result.from_computation(
            lambda: self._do_token_request(),
            ErrorCode.AUTHENTICATION_ERROR,
            "Access token acquisition failed",
        )
```

`Result.from_computation()` wraps any exception the inner function raises into a
`Result.failure(...)` — no try/except blocks needed in the calling code.

### 2. Pipeline chains results with `flat_map`

```python
# src/cert_parser/pipeline.py
def run_pipeline(...) -> Result[int]:
    return (
        access_token_provider.acquire_token()           # Result[str]
        .flat_map(_build_credentials)                   # Result[AuthCredentials]
        .flat_map(downloader.download)                  # Result[bytes]
        .flat_map(parser.parse)                         # Result[MasterListPayload]
        .flat_map(repository.store)                     # Result[int]
    )
```

If ANY step returns `Failure`, the `flat_map` chain short-circuits — downstream steps
are never called. This is the railway analogy: once you're on the failure track, you
stay there.

### 3. Tests use `ResultAssertions`

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

`assert_success()` returns the unwrapped value so you can continue asserting.
`assert_failure()` verifies the error code matches exactly.

### 4. Pattern matching for final consumption

```python
from railway import Result, Success, Failure

def handle_result(result: Result[int]) -> None:
    match result:
        case Success(rows):
            log.info("store.complete", rows_affected=rows)
        case Failure(error):
            log.error("store.failed", code=error.code.value, detail=error.message)
```

---

## ErrorCode Mapping to HTTP Status

The framework's `ErrorCode` enum maps directly to HTTP status codes, enabling clean
REST API responses in the ASGI app:

| ErrorCode | HTTP Status | Used When |
|-----------|------------|-----------|
| `VALIDATION_ERROR` | 400 | Malformed input |
| `AUTHENTICATION_ERROR` | 401 | Token acquisition failure |
| `AUTHORIZATION_ERROR` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource missing |
| `TECHNICAL_ERROR` | 500 | CMS parsing failure, ASN.1 errors |
| `DATABASE_ERROR` | 500 | PostgreSQL connection/query failure |
| `CONFIGURATION_ERROR` | 500 | Missing env vars |
| `EXTERNAL_SERVICE_ERROR` | 502 | ICAO download failure |
| `TIMEOUT_ERROR` | 504 | HTTP or DB timeout |

---

## Non-Negotiable Rules

These rules govern ALL use of the framework in cert-parser code:

1. **NEVER** use `try/except` in domain or pipeline code — use `Result.from_computation()` at adapter boundaries only
2. **NEVER** return `None` to signal failure — return `Result.failure(ErrorCode.X, "...")`
3. **ALWAYS** use `flat_map` to chain Result-returning operations
4. **ALWAYS** use `map` for infallible transformations of the success value
5. **ALWAYS** use `ensure` for conditional validation
6. **ALWAYS** use `peek` for logging without altering the Result
7. **ALWAYS** use `ResultAssertions` in tests — never unwrap manually with `.value()`

---

## Running Framework Tests

```bash
cd python_framework

# Install (with dev extras)
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=railway --cov-report=term-missing

# Expected: 100+ tests, all green
```

---

## Full API Reference

See **[python_framework/README.md](../../python_framework/README.md)** for:
- `Result[T]` API (creation, transformation, introspection, async)
- `ErrorCode` enum (all 13 codes)
- `ExecutionContext` protocol and implementations
- `ResultAssertions` test helper API
- HTTP response building (`build_fastapi_response`, `build_flask_response`)
- Handler → Data/Ports → Stages architecture pattern
- Comparison with other Python ROP libraries

---

## Related Documents

- [Error Handling & ROP](error-handling-rop.md) — how cert-parser uses ROP in practice
- [Architecture](architecture.md) — hexagonal/ports-and-adapters structure
- [Testing Strategy](testing-strategy.md) — `ResultAssertions` usage in all test layers
