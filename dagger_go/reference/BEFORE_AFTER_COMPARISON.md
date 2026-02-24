# Before / After: cert-parser CI/CD Evolution

## The Problem (Before)

Manual CI steps, inconsistent environments, tests that only worked on one developer's machine.

```bash
# Before: manual, fragile
pip install -e .[dev]
pytest tests/unit/
ruff check src/
mypy src/ --strict
docker build -t cert-parser .
docker push ghcr.io/username/cert-parser:latest
```

Problems:
- ❌ No reproducible environment
- ❌ Integration tests skipped ("it works on my machine")
- ❌ Docker push only ran if developer remembered
- ❌ No audit trail of what was tested before each image was pushed

---

## The Solution (After: Dagger Go Pipeline)

```bash
# After: one command, fully reproducible
./dagger_go/run.sh
```

The pipeline runs 7 stages in a reproducible Dagger container (plus host-based DB tests):

```
Stage 1: Unit Tests       → pytest -m "not integration and not acceptance"
Stage 2: Integration Tests → pytest -m integration        (host, testcontainers)
Stage 3: Acceptance Tests  → pytest -m acceptance          (host, testcontainers)
Stage 4: Lint              → ruff check src/ tests/ scripts/
Stage 5: Type Check        → mypy src/ --strict
Stage 6: Docker Build      → docker buildx build
Stage 7: Publish           → docker push ghcr.io/.../cert-parser:<tag>
```

---

## Stage-by-Stage Comparison

### Unit Tests

| | Before | After |
|-|--------|-------|
| Command | `pytest tests/unit/` | `pytest -m "not integration and not acceptance"` |
| Environment | Developer's local venv | Dagger container (python:3.14-slim, clean install) |
| Reproducible | ❌ Depends on local state | ✅ Always fresh container |
| Failure blocks publish | ❌ No | ✅ Yes |

### Integration Tests

| | Before | After |
|-|--------|-------|
| Command | Usually skipped | `pytest -m integration` |
| Database | Ad-hoc local Postgres | testcontainers (auto-managed) |
| Runs on | Host (if remembered) | Host (via `exec.Command` in pipeline) |
| Docker required | Manual setup | Auto-detected, skip gracefully if absent |

### Acceptance Tests

| | Before | After |
|-|--------|-------|
| Command | Almost never run | `pytest -m acceptance` |
| Environment | Mixed | Clean — pipeline-managed fixtures |
| Real data | Sometimes | Always (ICAO fixture `.bin` files) |

### Lint

| | Before | After |
|-|--------|-------|
| Command | `ruff check src/` | `ruff check src/ tests/ scripts/` |
| Scope | src only | src + tests + scripts |
| Blocks publish | ❌ | ✅ |

### Type Check

| | Before | After |
|-|--------|-------|
| Command | `mypy src/` | `mypy src/ --strict` |
| Strictness | Lenient | Strict (no implicit Any, full annotations) |
| Blocks publish | ❌ | ✅ |

### Docker Build + Publish

| | Before | After |
|-|--------|-------|
| Build | Manual `docker build` | Dagger-managed |
| Tag | `:latest` only | `v0.1.0-<sha7>-<timestamp>` + `:latest` |
| Publish | Manual `docker push` | Auto after all stages pass |
| Registry | Manual login | GHCR token from `credentials/.env` |

---

## Marker Annotations

### Before (no consistency)

```python
# Some tests had no markers — ran everywhere
def test_store_certificates():
    conn = psycopg.connect("postgresql://localhost:5432/testdb")  # hardcoded!
    ...
```

### After (explicit pytest markers)

```python
@pytest.mark.integration
def test_store_certificates(pg_dsn: str) -> None:
    """
    GIVEN a running PostgreSQL (testcontainers)
    WHEN certificates are stored
    THEN they are persisted correctly
    """
    repo = PsycopgCertificateRepository(dsn=pg_dsn)
    ...

@pytest.mark.acceptance
def test_full_pipeline(pg_dsn: str) -> None:
    """End-to-end: fixture .bin → parse → store → verify."""
    ...
```

---

## Selective Stage Execution

```bash
# Full pipeline
./dagger_go/run.sh

# Skip DB tests (faster iteration during development)
RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./dagger_go/run.sh

# Skip lint only (e.g. WIP branch)
RUN_LINT=false ./dagger_go/run.sh

# Skip type checking
RUN_TYPE_CHECK=false ./dagger_go/run.sh
```

---

## Image Tags Before vs After

| | Before | After |
|-|--------|-------|
| Format | `:latest` | `v0.1.0-abc1234-20250115-1430` + `:latest` |
| Traceability | ❌ No | ✅ Git SHA + timestamp embedded |
| Rollback | Pull `:latest` (might be old) | `docker pull ghcr.io/user/cert-parser:v0.1.0-abc1234-...` |

---

## Summary

The Dagger Go pipeline converts a fragile manual process into a single reproducible command.
All quality gates (test → lint → type-check → build → publish) are enforced in order,
with testcontainers-based DB tests running on the host to avoid Docker-in-Docker limitations.
