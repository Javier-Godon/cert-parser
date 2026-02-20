# Error Handling & Railway-Oriented Programming

## The Problem with Traditional Error Handling

Traditional Python code handles errors with `try/except`. This creates two problems:

1. **Exceptions are invisible** — you can't tell from a function signature whether it might fail
2. **Error handling is scattered** — try/except blocks at every call site, mixed with business logic

## Railway-Oriented Programming (ROP)

cert-parser uses the **railway-rop** framework (local, under `python_framework/`) to solve both problems.

### The Two-Track Railway

Every operation runs on a two-track railway:

```
  ┌───────────┐   flat_map    ┌───────────┐   flat_map    ┌──────────┐
  │ acquire   │──Success──────│ download  │──Success──────│  parse   │──→ Result[T]
  │  token    │               │   .bin    │               │    ML    │
  └─────┬─────┘               └─────┬─────┘               └─────┬────┘
        │ Failure                   │ Failure                   │ Failure
        └───────────────────────────┴───────────────────────────┴──→ Result[T]
```

- **Success track**: data flows forward through `flat_map` / `map`
- **Failure track**: errors propagate automatically — no try/except in business logic

### The Result Type

`Result[T]` is a sealed type with two variants:

```python
Success(value: T)                    # happy path
Failure(error: FailureDescription)   # error track
```

Every public function that can fail returns `Result[T]`. Never `None`, never exceptions.

### Core Operations

| Operation | When to use | Example |
|-----------|-------------|---------|
| `map(fn)` | Transform success value with infallible function | `result.map(lambda x: x * 2)` |
| `flat_map(fn)` | Chain a Result-returning function | `result.flat_map(parser.parse)` |
| `ensure(pred, err)` | Validate success value | `result.ensure(lambda x: x > 0, ...)` |
| `peek(fn)` | Side effect (logging) without altering result | `result.peek(lambda x: log.info(...))` |
| `either(on_s, on_f)` | Final consumption — branch on success/failure | `result.either(print, log_error)` |

### How flat_map Short-Circuits

```python
# If acquire_token fails → download, parse, store are NEVER called
token_provider.acquire_token()      # Result[str]
    .flat_map(downloader.download)  # only called if token succeeded
    .flat_map(parser.parse)         # only called if download succeeded
    .flat_map(repository.store)     # only called if parse succeeded
```

This is the **entire pipeline** — 4 lines of code, fully error-safe.

## ErrorCode Enum

Each failure has a typed error code:

```python
from railway import ErrorCode

ErrorCode.AUTHENTICATION_ERROR    # Token acquisition failures (401, network)
ErrorCode.EXTERNAL_SERVICE_ERROR  # Download failures (404, 500, timeout)
ErrorCode.TECHNICAL_ERROR         # Parse failures (invalid ASN.1, malformed CMS)
ErrorCode.DATABASE_ERROR          # Store failures (connection, constraint violation)
ErrorCode.VALIDATION_ERROR        # Data validation failures
ErrorCode.CONFIGURATION_ERROR     # Missing env vars
ErrorCode.TIMEOUT_ERROR           # HTTP or DB timeouts
```

## Result.from_computation()

This is the **bridge** between the exception world (library code) and the Result world (cert-parser business logic).

```python
def store(self, payload: MasterListPayload) -> Result[int]:
    return Result.from_computation(
        lambda: self._transactional_replace(payload),  # may raise
        ErrorCode.DATABASE_ERROR,                      # error code if it does
        "Failed to persist certificates to database",  # human message
    )
```

`from_computation` runs the lambda. If it succeeds, wraps the return value in `Result.success()`. If it raises ANY exception, catches it and wraps in `Result.failure(code, message + exception detail)`.

### Where from_computation Is Used

**Only at adapter boundaries** — the places where cert-parser code meets external libraries:

| Adapter | Method | Error Code |
|---------|--------|-----------|
| `HttpAccessTokenProvider` | `acquire_token()` | `AUTHENTICATION_ERROR` |
| `HttpSfcTokenProvider` | `acquire_token(access_token)` | `AUTHENTICATION_ERROR` |
| `HttpBinaryDownloader` | `download()` | `EXTERNAL_SERVICE_ERROR` |
| `CmsMasterListParser` | `parse()` | `TECHNICAL_ERROR` |
| `PsycopgCertificateRepository` | `store()` | `DATABASE_ERROR` |

### Where try/except Is NEVER Used

- **Domain layer** (models, ports) — never
- **Pipeline layer** — never
- **Inside adapter business logic** — never (only at the `from_computation` boundary)

## Error Handling by Layer

| Layer | Catches Exceptions? | Returns |
|-------|:-------------------:|---------|
| **Domain** (models, ports) | No | `Result[T]` |
| **Pipeline** | No | `Result[T]` via flat_map chain |
| **Adapters** | Yes, at boundary only | `Result[T]` via `from_computation()` |
| **Main** | Yes, last resort | Logs and exits |

## FailureDescription

When a failure occurs, it carries a `FailureDescription` with:

```python
@dataclass(frozen=True)
class FailureDescription:
    code: ErrorCode       # typed error code
    message: str          # human-readable message
    details: dict | None  # optional structured context
```

Access with `result.error()` (raises `ValueError` if called on Success).

## Consuming Results

### Pattern Matching (Preferred)

```python
match result:
    case Success(value):
        log.info("success", rows=value)
    case Failure(error):
        log.error("failure", code=error.code, message=error.message)
```

### either() Method

```python
result.either(
    on_success=lambda rows: log.info("success", rows=rows),
    on_failure=lambda err: log.error("failure", error=str(err)),
)
```

### Direct Access (Use with Caution)

```python
result.value()  # raises ValueError if Failure
result.error()  # raises ValueError if Success
```

## Testing with ResultAssertions

The railway framework provides assertion helpers:

```python
from railway import ResultAssertions, ErrorCode

# Assert success and get value
payload = ResultAssertions.assert_success(result)
assert payload.total_certificates > 0

# Assert failure with specific error code
ResultAssertions.assert_failure(result, ErrorCode.TECHNICAL_ERROR)

# Assert failure message contains text
ResultAssertions.assert_failure_message_contains(result, "CMS")
```

## LoggingExecutionContext

The scheduler wraps pipeline execution in a `LoggingExecutionContext`:

```python
ctx = LoggingExecutionContext(operation="MasterListSync")
result = ctx.execute(lambda: sync_pipeline(ports))
```

This automatically logs:
- Start time and operation name
- Duration on completion
- Success/failure status
- Error details on failure

The pipeline itself remains pure — logging is a cross-cutting concern handled externally.
