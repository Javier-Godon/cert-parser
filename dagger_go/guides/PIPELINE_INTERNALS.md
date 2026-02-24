# cert-parser Pipeline Internals — main.go

**Status**: ✅ Complete and Production Ready

## What This Is

The Dagger Go pipeline in `main.go` runs the full cert-parser CI/CD cycle inside
a `python:3.14-slim` container, with integration and acceptance tests running on the
**host machine** via testcontainers (native Docker socket required).

### Pipeline Flow

```
Clone Repository
    ↓
🔍 Discover project name from pyproject.toml
    ↓
🔍 Check Docker Availability (for testcontainers)
    ↓
🔨 Set up Python build environment in Dagger container
    ├─ pip install -e ./python_framework   (local railway-rop dependency)
    └─ pip install -e .[dev,server]
    ↓
🧪 STAGE: Unit Tests (in Dagger container)
    ├─ pytest -m "not integration and not acceptance"
    └─ Fast — no Docker needed
    ↓
🧪 STAGE: Integration Tests (on HOST machine)
    ├─ Docker available → pytest -m integration (testcontainers/PostgreSQL)
    └─ Docker missing  → SKIPPED with warning
    ↓
🧪 STAGE: Acceptance Tests (on HOST machine)
    ├─ Docker available → pytest -m acceptance (testcontainers/PostgreSQL)
    └─ Docker missing  → SKIPPED with warning
    ↓
🔍 STAGE: Lint — ruff check src/ tests/
    ↓
🔍 STAGE: Type Check — mypy src/ --strict
    ↓
🐳 STAGE: Build Docker image (from Dockerfile)
    ↓
📤 STAGE: Publish to GHCR (versioned + latest tags)
```

---

## Key Components

### 1. Constants

```go
const (
    baseImage                 = "python:3.14-slim"
    appWorkdir                = "/app"
    containerDockerSocketPath = "/var/run/docker.sock"
    dockerUnixPrefix          = "unix://"
    separatorLine             = "─────────────────..."
)
```

### 2. Pipeline Struct

```go
type Pipeline struct {
    RepoName            string
    ProjectName         string          // auto-discovered from pyproject.toml
    ImageName           string          // Docker-safe form of ProjectName
    GitRepo             string
    GitBranch           string
    GitUser             string
    PipCache            *dagger.CacheVolume
    RunUnitTests        bool            // RUN_UNIT_TESTS (default: true)
    RunIntegrationTests bool            // RUN_INTEGRATION_TESTS (default: true)
    RunAcceptanceTests  bool            // RUN_ACCEPTANCE_TESTS (default: true)
    RunLint             bool            // RUN_LINT (default: true)
    RunTypeCheck        bool            // RUN_TYPE_CHECK (default: true)
    HasDocker           bool            // Docker available for testcontainers
}
```

### 3. Project Name Auto-Discovery

```go
// extractProjectName parses name = "..." from pyproject.toml content.
func extractProjectName(content string) string {
    re := regexp.MustCompile(`(?m)^name\s*=\s*"([^"]+)"`)
    matches := re.FindStringSubmatch(content)
    ...
}
```
The pipeline reads `pyproject.toml` from the cloned source directly — no hardcoded
project name anywhere.

### 4. Docker Socket Detection (for testcontainers)

```go
func getDockerSocketPath() string {
    // Checks platform-appropriate candidates:
    //   Linux:  /var/run/docker.sock, /run/docker.sock, $DOCKER_HOST
    //   macOS:  ~/.docker/run/docker.sock, ~/.colima/docker.sock
    //   Windows: named pipe paths
}
```
If Docker is unavailable, integration and acceptance tests are **skipped** (not failed).

### 5. Python Build Environment (Dagger container)

```go
builder := client.Container().
    From(baseImage).                         // python:3.14-slim
    WithExec([]string{"apt-get", "update"}).
    WithExec([]string{"apt-get", "install", "-y",
        "git", "build-essential", "libpq-dev"}).
    WithMountedCache("/root/.cache/pip", p.PipCache).
    WithMountedDirectory(appWorkdir, source).
    WithWorkdir(appWorkdir).
    WithExec([]string{"pip", "install", "--upgrade", "pip"}).
    // Install local framework first (cert-parser depends on railway-rop)
    WithExec([]string{"pip", "install", "-e", "./python_framework"}).
    WithExec([]string{"pip", "install", "-e", ".[dev,server]"})
```

### 6. Unit Tests (in Dagger container)

```go
testContainer := builder.WithExec([]string{
    "pytest", "-v", "--tb=short",
    "-m", "not integration and not acceptance",
})
```
Runs inside the Dagger container — fast, isolated, no Docker socket needed.

### 7. Integration/Acceptance Tests (on HOST)

```go
func (p *Pipeline) runTestsOnHost(ctx context.Context, marker string) error {
    // Finds project root (dagger_go/../)
    // Prefers .venv/bin/pytest, falls back to system pytest
    // Runs: pytest -v --tb=short -m <marker>
    // Streams output to stdout in real-time
}
```

**Why on host?** Testcontainers needs native Docker socket access. Inside
Dagger containers, Docker socket path remapping breaks volume mounts.

### 8. Host Test Summary Parsing

```go
func displayHostTestSummary(marker, output string, duration time.Duration, testErr error)
```
Parses pytest's summary line (`X passed, Y failed`) and prints structured output.

---

## Environment Variables

### Required
- `CR_PAT` — GitHub Container Registry PAT
- `USERNAME` — GitHub username

### Pipeline Stage Flags (all default `true`)
| Variable | Default | Description |
|---|---|---|
| `RUN_UNIT_TESTS` | `true` | pytest unit tests in Dagger container |
| `RUN_INTEGRATION_TESTS` | `true` | pytest integration tests on host |
| `RUN_ACCEPTANCE_TESTS` | `true` | pytest acceptance tests on host |
| `RUN_LINT` | `true` | ruff check |
| `RUN_TYPE_CHECK` | `true` | mypy strict |

### Optional
| Variable | Description |
|---|---|
| `REPO_NAME` | Repository name (auto-detected from parent dir if unset) |
| `GIT_BRANCH` | Branch to build (default: `main`) |
| `IMAGE_NAME` | Docker image name (default: Docker-safe project name) |

---

## Python Test Setup

Tests use `pytest` markers to control which tests run where:

```python
# conftest.py / pyproject.toml
markers:
  integration  — requires PostgreSQL via testcontainers
  acceptance   — full pipeline end-to-end with real fixtures + real DB
```

Integration and acceptance tests use `testcontainers[postgres]`:

```python
@pytest.mark.integration
def test_store_and_retrieve(pg_container):
    # testcontainers spins up a real PostgreSQL on a random port
    dsn = pg_container.get_connection_url()
    repo = PsycopgCertificateRepository(dsn=dsn)
    ...
```

---

## Performance Profile

| Stage | Location | Duration | Docker |
|-------|----------|----------|--------|
| Clone + discover | Dagger | ~10s | No |
| Python install | Dagger | ~30s first / ~5s cached | No |
| Unit tests | Dagger | ~15s | No |
| Integration tests | Host | ~30-60s | Yes |
| Acceptance tests | Host | ~30-60s | Yes |
| Lint (ruff) | Dagger | ~3s | No |
| Type check (mypy) | Dagger | ~10s | No |
| Docker build | Dagger | ~30s first / ~5s cached | No |
| Publish to GHCR | Dagger | ~15s | No |
| **Total** | | **~3-5 min first / ~1-2 min cached** | Optional |

---

## Error Handling

| Condition | Behaviour |
|---|---|
| Docker unavailable | Integration/acceptance tests skipped with warning |
| Unit test failure | Pipeline aborts — no lint/build/publish |
| Lint failure | Pipeline aborts — no build/publish |
| Type check failure | Pipeline aborts — no build/publish |
| Build failure | Pipeline aborts — no publish |
| Publish failure | Error reported, pipeline fails |

---

## Code Statistics

- **Lines**: ~570 lines of Go
- **Stages**: 7 configurable stages
- **Binary size**: ~20 MB
- **Compilation**: ✅ Successful — `go build -o cert-parser-dagger-go main.go`

---

**Status**: ✅ **PRODUCTION READY**
**Implementation**: Unit tests in container + Integration/Acceptance on host (testcontainers)
