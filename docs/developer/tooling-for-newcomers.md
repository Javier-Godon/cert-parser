# Technology Stack — Explained for Newcomers

> This document explains **what each technology is and why we use it**, in plain language.  
> If you already know Python web development, skip to the sections you need.  
> For the deeper rationale behind library selection, see [Libraries & Tooling](libraries-and-tooling.md).

---

## Table of Contents

1. [ASGI, FastAPI, and Uvicorn](#asgi-fastapi-and-uvicorn)
2. [ruff — Linter & Formatter](#ruff--linter--formatter)
3. [mypy — Static Type Checker](#mypy--static-type-checker)
4. [Railway-Oriented Programming (railway-rop)](#railway-oriented-programming-railway-rop)
5. [psycopg v3 — PostgreSQL Driver](#psycopg-v3--postgresql-driver)
6. [APScheduler — Job Scheduler](#apscheduler--job-scheduler)
7. [pydantic-settings — Configuration](#pydantic-settings--configuration)
8. [structlog — Structured Logging](#structlog--structured-logging)
9. [tenacity — Retry & Backoff](#tenacity--retry--backoff)
10. [testcontainers — Integration Testing](#testcontainers--integration-testing)
11. [respx — HTTP Mocking](#respx--http-mocking)
12. [asn1crypto & cryptography — Certificate Parsing](#asn1crypto--cryptography--certificate-parsing)
13. [httpx — HTTP Client](#httpx--http-client)

---

## ASGI, FastAPI, and Uvicorn

### What is ASGI?

**ASGI** stands for *Asynchronous Server Gateway Interface*. It is the Python standard that
defines how a web server and a Python web application talk to each other.

Think of it as a contract:

```
Browser / Kubernetes probe / curl
         │
         ▼
┌────────────────────┐
│   Uvicorn (server) │  ← listens for HTTP requests, handles signals (SIGTERM)
└────────┬───────────┘
         │  ASGI protocol (function call)
         ▼
┌────────────────────┐
│   FastAPI (app)    │  ← your business logic: routes, health checks
└────────────────────┘
```

**WSGI** (the older standard used by Flask/Django) is synchronous — one request at a time
per thread. **ASGI** supports async I/O and concurrent requests without threads.

---

### What is Uvicorn?

**Uvicorn** is the production **web server** — the program that listens on port 8000 and
accepts HTTP connections. It implements the ASGI standard.

Key features relevant to us:

| Feature | Benefit |
|---------|---------|
| **SIGTERM handling** | Kubernetes sends SIGTERM to stop a pod; Uvicorn catches it and drains in-flight requests before exiting |
| **Single worker mode** | We run `--workers 1` so APScheduler isn't accidentally forked into multiple processes |
| **Low overhead** | Built on `uvloop` + `httptools` — fast enough for Kubernetes health probes |

In our codebase, `cert_parser/asgi.py` defines the `app` object. Uvicorn loads it with:
```
python -m uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1
```

---

### What is FastAPI?

**FastAPI** is a Python **web framework** — it gives us HTTP route definitions, request
parsing, and JSON responses with minimal boilerplate. We use it for:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe — Kubernetes checks every 30s to ensure the process is alive |
| `GET /ready` | Readiness probe — reports "ready" after the first successful pipeline run |
| `GET /info` | Version, config summary, uptime |
| `POST /trigger` | Manual pipeline trigger (for testing via Postman / curl) |

FastAPI is also responsible for the **lifespan** events — code that runs when the server
starts up (create adapters, start APScheduler) and shuts down (stop scheduler gracefully).

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup — runs before first request
    scheduler.start()
    yield
    # Shutdown — runs when Uvicorn gets SIGTERM
    scheduler.shutdown()
```

---

### How asgi.py ties it together

`cert_parser/asgi.py` is the **ASGI entry point**. It:

1. Loads configuration (`AppSettings`)
2. Creates all adapters (HTTP client, CMS parser, PostgreSQL repository)
3. Creates the pipeline function (partially applied, with all adapters injected)
4. Starts APScheduler in a background thread
5. Exposes FastAPI routes for health/readiness/manual trigger

```
Uvicorn starts
    → imports cert_parser.asgi
    → calls lifespan
        → AppSettings loads env vars
        → adapters created (HttpClient, CmsParser, Repository)
        → APScheduler starts (background thread)
    → FastAPI serves /health, /ready, /info, /trigger
```

---

## ruff — Linter & Formatter

### What is a linter?

A **linter** reads your source code and reports problems — style issues, probable bugs,
unused imports, overly complex expressions — WITHOUT running the code. It is like a spell
checker, but for code quality.

### What is a formatter?

A **formatter** automatically rewrites your code to follow consistent style rules
(indentation, line length, quote style, etc.). You don't argue about formatting in code
review — the formatter decides.

### What is ruff?

**ruff** is a modern Python linter AND formatter written in Rust. It is:

- Extremely fast (10–100x faster than older tools like `flake8` + `black`)
- A drop-in replacement for `flake8`, `isort`, `pyupgrade`, and `black` all at once
- Configured in `pyproject.toml`

```toml
# pyproject.toml
[tool.ruff]
line-length = 100          # lines longer than 100 chars are flagged

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]   # Error, pyFlakes, isort, pyUpgrade
```

**How to run it:**

```bash
# Check for issues (no changes)
ruff check src/ tests/

# Apply automatic fixes
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/

# Check and format in one pass
ruff check --fix src/ tests/ && ruff format src/ tests/
```

**In development**, your editor likely runs ruff on save automatically. In CI (the Dagger
pipeline), ruff runs as a mandatory stage — if it reports any errors, the pipeline fails.

---

## mypy — Static Type Checker

### What is static type checking?

Python's type hints (`def foo(x: int) -> str:`) are just annotations — Python itself does
not enforce them at runtime. A **static type checker** reads your code and verifies that
every function call is passed the right types, every variable holds what you think it holds,
and every return value matches the declared type.

**Without mypy:**
```python
def get_name(user_id: int) -> str:
    return None  # ← No runtime error. This returns None, not a str.
```

**With mypy strict:**
```
error: Incompatible return value type (got "None", expected "str")
```

### What is `--strict` mode?

Strict mode enables ALL mypy checks including:
- No implicit `Any` types (everything must be typed)
- No untyped function definitions
- No untyped module imports

This is appropriate for production code because it catches the most bugs.

```bash
# Run in CI and before commits
mypy src/ --strict
```

**In this project:** mypy reads the `[tool.mypy]` section of `pyproject.toml`.

---

## Railway-Oriented Programming (railway-rop)

This is our most distinctive technology choice. For a full explanation see:
- [Error Handling & ROP](error-handling-rop.md) — how we use it in the application
- [python_framework/README.md](../../python_framework/README.md) — the framework reference

**In one sentence**: instead of functions that sometimes raise exceptions and sometimes
return values, EVERY function that can fail returns a `Result[T]` — either
`Success(value)` or `Failure(error_code, message)`. Errors propagate automatically
through `flat_map` chains without try/except blocks.

```python
# Traditional Python — exceptions hidden in signatures
def run():
    token = get_token()       # might raise anything
    data = download(token)    # might raise anything
    store(data)               # might raise anything

# ROP — all failure paths explicit
def run() -> Result[int]:
    return (
        get_token()           # → Result[str]
        .flat_map(download)   # → Result[bytes]
        .flat_map(parse)      # → Result[MasterListPayload]
        .flat_map(store)      # → Result[int]
    )
```

---

## psycopg v3 — PostgreSQL Driver

**psycopg** is the standard PostgreSQL driver for Python. Version 3 (our choice) is the
modern rewrite with:

- Native async support (though we use sync)
- Better type mapping (UUID, BYTEA, TIMESTAMP map directly to Python types)
- `conn.transaction()` context manager for clean ACID transactions
- Binary protocol support (faster for BYTEA columns like our certificate bytes)

```bash
pip install "psycopg[binary,pool]>=3.3.0"
```

We use the `binary` extra for compiled C extensions (faster), and `pool` for connection
pooling support (used in the ASGI server).

---

## APScheduler — Job Scheduler

**APScheduler** (Advanced Python Scheduler) is a lightweight in-process job scheduler.
We use it to trigger the pipeline automatically every N hours.

Unlike cron (which is an OS-level concept), APScheduler runs **inside** the Python process:

```
cert-parser process
├── Uvicorn main thread    → serves HTTP (/health, /ready, /trigger)
└── APScheduler thread     → wakes up every 6h, calls run_pipeline()
```

We pin it to `>=3.11.0, <4.0` because version 4 is an almost complete API rewrite and not
yet stable.

```python
scheduler = BlockingScheduler()
scheduler.add_job(
    run_pipeline,
    trigger=CronTrigger.from_crontab(settings.scheduler.cron),
    id="cert_parser_job",
)
scheduler.start()  # blocks; catches SIGTERM for graceful shutdown
```

---

## pydantic-settings — Configuration

**pydantic-settings** reads environment variables (or `.env` files) and validates them into
typed Python objects. Instead of `os.getenv("AUTH_URL", "")` scattered throughout the code,
all configuration lives in one place:

```python
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",  # AUTH__URL=... becomes settings.auth.url
    )

    class AuthSettings(BaseModel):
        url: str
        username: str
        password: SecretStr  # masked in logs

    auth: AuthSettings
```

With `env_nested_delimiter="__"`:
- `AUTH__URL=https://...` → `settings.auth.url`
- `DATABASE__HOST=localhost` → `settings.database.host`

This is the standard pattern for Kubernetes ConfigMap + Secret injection.

---

## structlog — Structured Logging

Standard Python logging produces lines like:

```
2026-03-01 10:00:00 INFO Downloaded 524288 bytes in 1234ms
```

This is hard to parse in a log aggregator (ELK, Datadog, CloudWatch).

**structlog** produces **structured JSON**:

```json
{"timestamp": "2026-03-01T10:00:00Z", "level": "info", "event": "download.complete", "size_bytes": 524288, "duration_ms": 1234}
```

Every key-value pair is queryable. You can filter all log lines where `duration_ms > 5000`
in one query, without regex parsing.

In development, structlog renders colored, human-readable output. In production (Docker),
it renders JSON. This is configured in `main.py` via `configure_structlog(log_level)`.

**Naming convention**: event names use `module.action` format:
- `pipeline.started`, `download.complete`, `store.failed`

---

## tenacity — Retry & Backoff

**tenacity** is a library that retries a function call when it fails, with configurable
wait time between retries.

Why do we need this? Network operations (HTTP requests to the ICAO auth server, to the
download endpoint) can fail transiently — the server might be temporarily overloaded, the
network might hiccup. A single retry often solves these problems.

```python
@retry(
    stop=stop_after_attempt(3),              # give up after 3 total attempts
    wait=wait_exponential(min=2, max=30),    # wait 2s, 4s, 8s, 16s, ...
    retry=retry_if_exception_type(           # only retry network errors
        (httpx.TimeoutException, httpx.NetworkError)
    ),
    reraise=True,  # let Result.from_computation() catch the final failure
)
def _do_token_request(self) -> str:
    ...
```

**Key rule**: tenacity decorates the **private inner method** (the one that raises
exceptions), NOT the public `Result`-returning method. The retry loop exhausts itself,
then the exception propagates to `Result.from_computation()` which converts it to
`Result.failure(AUTHENTICATION_ERROR, ...)`.

---

## testcontainers — Integration Testing

**testcontainers** is a library that starts real Docker containers during tests and stops
them afterwards. We use it to spin up a real PostgreSQL database for integration and
acceptance tests.

```python
from testcontainers.postgres import PostgresContainer

def test_repository_stores_certificates():
    with PostgresContainer("postgres:16") as pg:
        dsn = pg.get_connection_url()
        repo = PsycopgCertificateRepository(dsn)
        result = repo.store(sample_payload)
        assert result.is_success()
```

When the test finishes, the PostgreSQL container is automatically stopped and destroyed.
No shared database, no leftover state between tests.

**Why does this matter for the CI pipeline?** testcontainers needs to talk to a real Docker
daemon. Inside a Dagger container (Docker-in-Docker), the socket paths are remapped in a way
that breaks testcontainers' volume mounts. That is why integration and acceptance tests run
on the **host machine**, not inside the Dagger build container. See
[CI/CD Pipeline](cicd-pipeline.md) for details.

---

## respx — HTTP Mocking

**respx** is a library for mocking `httpx` HTTP calls in unit tests. Without it, every
test that uses `HttpAccessTokenProvider`, `HttpBinaryDownloader`, etc. would make real
HTTP calls to the ICAO server — which is slow, fragile, and not repeatable.

```python
import respx
import httpx

@respx.mock
def test_acquire_token_success():
    respx.post("https://auth.example.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "abc123"})
    )
    provider = HttpAccessTokenProvider(settings)
    result = provider.acquire_token()
    assert result.is_success()
    assert result.value() == "abc123"
```

**In production**: respx is never imported. It is a `[dev]` dependency only.

---

## asn1crypto & cryptography — Certificate Parsing

This is our key architectural decision. Neither library alone is sufficient.

| Library | What it does | Why we need both |
|---------|--------------|-----------------|
| **asn1crypto** | Parses CMS/PKCS#7 envelopes; gives access to `eContent`, outer `certificates`, and `crls` | `cryptography` cannot access `eContent` or the CMS certificate SET |
| **cryptography** (PyCA) | Parses X.509 certificates; extracts SKI, AKI, issuer, serial number | `asn1crypto`'s X.509 API is less refined for extension extraction |

See [Libraries & Tooling](libraries-and-tooling.md) for full details.

---

## httpx — HTTP Client

**httpx** is a modern Python HTTP client. We use it in `HttpAccessTokenProvider`,
`HttpSfcTokenProvider`, and `HttpBinaryDownloader`.

Why httpx over `requests`:

| Capability | requests | httpx |
|-----------|---------|-------|
| Sync API | ✅ | ✅ |
| Async API | ❌ | ✅ |
| HTTP/2 | ❌ | ✅ (with `[http2]` extra) |
| Streaming responses | Partial | ✅ |
| Type annotations | Limited | Complete |
| Active maintenance | Maintenance-only | Active |

We use `httpx[http2]` and the synchronous client (the ASGI server is async, but the
pipeline itself runs in a background thread and uses sync I/O).

---

## Dependency Version Philosophy

Every dependency in `pyproject.toml` has a documented rationale:

```toml
"httpx[http2] >= 0.28.1",         # minimum tested version
"APScheduler >= 3.11.0, < 4.0",   # upper bound — v4 is a breaking rewrite
"pydantic >= 2.12.0",              # v2 only — v1 API is incompatible
```

**Upper bounds** are set only where the next major version is a known breaking change.
For all other packages we use minimum bounds to allow security patches to flow in.

---

## Related Documents

- [Libraries & Tooling](libraries-and-tooling.md) — deeper dive into asn1crypto, cryptography, httpx
- [Error Handling & ROP](error-handling-rop.md) — how Result and flat_map work in practice
- [Dockerfile](dockerfile.md) — how all of this is packaged for production
- [Testing Strategy](testing-strategy.md) — unit / integration / acceptance test layers
- [python_framework README](../../python_framework/README.md) — railway-rop API reference
