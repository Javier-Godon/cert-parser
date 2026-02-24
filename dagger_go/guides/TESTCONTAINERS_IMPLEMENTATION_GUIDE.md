# Testcontainers Implementation Guide

## Why Tests Run on the Host (Not in Dagger)

Testcontainers-Python spins up real Docker containers (PostgreSQL) during test execution.
Inside a Dagger pipeline, containers run in a Docker-in-Docker environment where:

- Volume mount paths are remapped by Dagger's container runtime
- The Docker socket path differs from the host (`/var/run/docker.sock`)
- Testcontainers' internal lifecycle management breaks due to path mismatches

**Solution**: Integration and acceptance tests run on the **host machine** via
`exec.Command` in `main.go`. The Dagger container only runs unit tests.

---

## Architecture: Three Test Tiers

```
┌─────────────────────────────────────────────────────────────┐
│  Dagger Container (python:3.14-slim)                         │
│  ┌──────────────────────────────────────┐                   │
│  │  Unit Tests (Stage 1)               │                   │
│  │  pytest -m "not integration         │                   │
│  │          and not acceptance"        │                   │
│  │  No Docker, no network needed       │                   │
│  └──────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Host Machine (native Docker socket)                         │
│  ┌──────────────────────────────────────┐                   │
│  │  Integration Tests (Stage 2)        │                   │
│  │  pytest -m integration              │ ← testcontainers   │
│  │  ┌──────────────────────┐          │   spins up here    │
│  │  │ PostgreSQL container │          │                   │
│  │  │ (testcontainers)     │          │                   │
│  │  └──────────────────────┘          │                   │
│  └──────────────────────────────────────┘                   │
│                                                             │
│  ┌──────────────────────────────────────┐                   │
│  │  Acceptance Tests (Stage 3)         │ ← testcontainers   │
│  │  pytest -m acceptance               │   spins up here    │
│  │  ┌──────────────────────┐          │                   │
│  │  │ PostgreSQL container │          │                   │
│  │  └──────────────────────┘          │                   │
│  └──────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## How `runTestsOnHost()` Works (`main.go`)

```go
func (p *Pipeline) runTestsOnHost(ctx context.Context, marker string) (string, error) {
    projectRoot := filepath.Dir(p.ProjectDir) // parent of dagger_go/

    // Prefer virtualenv pytest, fall back to system pytest
    pytest := filepath.Join(projectRoot, ".venv", "bin", "pytest")
    if _, err := os.Stat(pytest); os.IsNotExist(err) {
        pytest = "pytest"
    }

    // Stream output in real-time while capturing for summary
    cmd := exec.CommandContext(ctx, pytest, "-v", "--tb=short", "-m", marker)
    cmd.Dir = projectRoot
    cmd.Stdout = io.MultiWriter(os.Stdout, &outputBuffer)
    cmd.Stderr = os.Stderr
    return outputBuffer.String(), cmd.Run()
}
```

### Docker Socket Detection

```go
func getDockerSocketPath() (string, bool) {
    candidates := []string{
        "/var/run/docker.sock",                              // Linux
        filepath.Join(os.Getenv("HOME"), ".docker/run/docker.sock"), // macOS Docker Desktop
        "/var/run/docker.sock.raw",                          // Colima
    }
    for _, p := range candidates {
        if _, err := os.Stat(p); err == nil {
            return p, true
        }
    }
    return "", false
}
```

---

## Environment Setup for Integration/Acceptance Tests

The tests need `CERT_PARSER_` environment variables available. The pipeline inherits
the host's environment, so tests pick up variables from `.env` via `pytest-dotenv`
or `pydantic-settings`' own `.env` loading.

Alternatively, set them explicitly in `credentials/.env`:

```bash
# credentials/.env (gitignored)
CR_PAT=ghp_...
USERNAME=your-github-username
# These are passed to host pytest via pipeline's os.Environ inheritance
DATABASE_HOST=localhost   # testcontainers overrides DSN anyway
```

---

## Configuring Test Execution

```bash
# Skip integration tests (faster pipeline iteration)
RUN_INTEGRATION_TESTS=false ./run.sh

# Skip acceptance tests  
RUN_ACCEPTANCE_TESTS=false ./run.sh

# Skip both (only unit tests + lint + type-check + Docker build)
RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh

# Run everything
./run.sh
```

---

## Adding a New Integration Test

1. Create `tests/integration/test_<feature>.py`
2. Decorate with `@pytest.mark.integration`
3. Use the shared `pg_dsn` fixture from `tests/conftest.py`
4. Write a Given/When/Then docstring

```python
@pytest.mark.integration
def test_transactional_rollback_preserves_old_data(pg_dsn: str) -> None:
    """
    GIVEN a database with existing certificate data
    WHEN store() is called with malformed payload that causes a DB error
    THEN the original data is preserved (ACID rollback)
    """
    ...
```

---

## Troubleshooting

### "Connection refused" to PostgreSQL

Testcontainers starts on a random host port. Always use the DSN from the fixture:

```python
# ✅ Correct — uses dynamic port assigned by testcontainers
def test_something(pg_dsn: str) -> None:
    repo = PsycopgCertificateRepository(dsn=pg_dsn)

# ❌ Wrong — hardcoded port will fail
def test_something() -> None:
    repo = PsycopgCertificateRepository(dsn="postgresql://localhost:5432/test")
```

### Tests Hang on CI

Ensure Docker is available in your CI environment:

```yaml
# GitHub Actions
jobs:
  test:
    runs-on: ubuntu-latest
    # Docker daemon is already available on ubuntu-latest runners
    steps:
      - uses: actions/checkout@v4
      - name: Run pipeline
        run: ./dagger_go/run.sh
        env:
          CR_PAT: ${{ secrets.CR_PAT }}
          USERNAME: ${{ github.actor }}
```

### Skipping Without Failure

The pipeline treats missing Docker as a skip, not a failure:

```
⏭️  Docker not available — skipping integration tests (testcontainers requires native Docker)
⏭️  Docker not available — skipping acceptance tests (testcontainers requires native Docker)
```

Unit tests, lint, and type-check still run and can fail the pipeline.
