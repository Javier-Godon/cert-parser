# Implementation Quick Start: Testcontainers in Python Dagger Pipeline

## 5-Minute Summary

The cert-parser pipeline uses **testcontainers-python** for integration and acceptance tests,
running them on the **host machine** (not inside the Dagger container) because
testcontainers needs native Docker socket access.

---

## How Tests Are Split

| Marker | Runs In | Tool | Needs Docker |
|--------|---------|------|-------------|
| `not integration and not acceptance` | Dagger container | pytest | No |
| `integration` | Host machine | pytest + testcontainers | Yes |
| `acceptance` | Host machine | pytest + testcontainers | Yes |

---

## Writing Integration Tests

```python
# tests/integration/test_repository.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.mark.integration
def test_store_certificates(pg_dsn: str) -> None:
    """
    GIVEN a running PostgreSQL instance (testcontainers)
    WHEN we store a MasterListPayload via PsycopgCertificateRepository
    THEN the rows are persisted and can be verified
    """
    from cert_parser.adapters.repository import PsycopgCertificateRepository
    repo = PsycopgCertificateRepository(dsn=pg_dsn)
    ...
```

### Shared Fixture (conftest.py)

```python
# tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def pg_dsn(pg_container) -> str:
    return pg_container.get_connection_url().replace("postgresql+psycopg2", "postgresql")
```

---

## Writing Acceptance Tests

```python
# tests/acceptance/test_pipeline_e2e.py
import pytest
from railway import ResultAssertions

@pytest.mark.acceptance
def test_full_pipeline_with_real_fixtures(pg_dsn: str) -> None:
    """
    GIVEN a valid ICAO Master List fixture (ml_sc.bin)
    WHEN the full pipeline runs (mock HTTP → real parser → real DB)
    THEN rows are stored and verifiable in PostgreSQL
    """
    raw_bin = (Path("tests/fixtures") / "ml_sc.bin").read_bytes()
    # ... run pipeline with mock HTTP adapter pointing at fixture bytes
```

---

## Running Tests Locally

```bash
# Unit tests (no Docker)
pytest -m "not integration and not acceptance" -v

# Integration tests (needs Docker)
pytest -m integration -v

# Acceptance tests (needs Docker)
pytest -m acceptance -v

# Full suite
pytest -v
```

---

## Pipeline Invocation

The Go pipeline invokes host-machine tests via `exec.Command`:

```go
// runTestsOnHost — simplified
cmd := exec.CommandContext(ctx, ".venv/bin/pytest",
    "-v", "--tb=short", "-m", marker)  // marker = "integration" | "acceptance"
cmd.Dir = projectRoot
cmd.Stdout = multiWriter   // streams to stdout in real-time
cmd.Stderr = os.Stderr
err = cmd.Run()
```

Integration/acceptance tests are skipped (not failed) when Docker is unavailable:

```go
if p.RunIntegrationTests && p.HasDocker {
    // run on host
} else if p.RunIntegrationTests && !p.HasDocker {
    fmt.Println("⏭️  Docker not available — testcontainers cannot start PostgreSQL")
}
```

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| "Cannot connect to Docker daemon" | Docker not running | Start Docker Desktop or daemon |
| "Port already in use" | Leftover testcontainer | `docker ps` and remove stale containers |
| "testcontainers: waiting for container" timeout | Slow pull | `docker pull postgres:16-alpine` first |
| Tests pass locally but skipped in CI | No Docker in CI | Set up Docker-in-Docker or GitHub Actions Docker service |

---

## Verification Checklist

- [ ] `pytest -m "not integration and not acceptance"` passes in Dagger container
- [ ] `pytest -m integration` passes on host with Docker running
- [ ] `pytest -m acceptance` passes on host with Docker running
- [ ] `RUN_INTEGRATION_TESTS=false ./run.sh` skips integration tests correctly
- [ ] Pipeline gracefully skips integration/acceptance when Docker unavailable
