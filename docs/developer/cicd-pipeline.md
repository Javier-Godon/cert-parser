# CI/CD Pipeline — Dagger Go SDK

> This document explains the automated CI/CD pipeline for cert-parser: what Dagger is,
> how both the standard and corporate pipelines work, how to run them, and why certain
> design decisions were made.

---

## Table of Contents

1. [What Is Dagger?](#what-is-dagger)
2. [Pipeline Overview](#pipeline-overview)
3. [Standard Pipeline (`main.go`)](#standard-pipeline-maingo)
4. [Corporate Pipeline (`corporate_main.go`)](#corporate-pipeline-corporate_maingo)
5. [Where Tests Run — The Testcontainers Problem](#where-tests-run--the-testcontainers-problem)
6. [Running the Pipeline](#running-the-pipeline)
7. [Configuration Reference](#configuration-reference)
8. [Pipeline Internals](#pipeline-internals)
9. [Build Artifacts](#build-artifacts)
10. [Troubleshooting](#troubleshooting)

---

## What Is Dagger?

**Dagger** is a programmable CI/CD engine. Unlike traditional CI systems (Jenkins, GitHub
Actions, GitLab CI) that define pipelines in YAML files, Dagger lets you write pipelines
in real programming languages — in our case, **Go**.

### Why Dagger + Go (not YAML)?

| Concern | YAML CI | Dagger Go |
|---------|---------|-----------|
| **Testability** | CI config untestable locally | `go test` tests every utility function |
| **Type safety** | Strings everywhere; typos break pipelines | Go compiler catches errors before running |
| **Portability** | Pipeline runs only in the CI server | Same binary runs on developer laptops |
| **Debugging** | `git push` to see logs; CI-specific tricks | `go run .` locally, full IDE debugging |
| **Logic** | Bash embedded in YAML | Real Go: loops, error handling, conditions |

### What Is the Dagger Go SDK?

The **Dagger Go SDK** (`dagger.io/dagger`) is a Go library that lets you describe container
operations as Go function calls. The Dagger engine (a daemon process) executes the graph of
operations, caching intermediate results.

```go
// This Go code describes a container operation — no shell, no YAML
container := client.Container().
    From("python:3.14-slim").
    WithExec([]string{"pip", "install", "pytest"}).
    WithMountedDirectory("/app", source).
    WithExec([]string{"pytest", "-v"})

output, err := container.Stdout(ctx)
```

The Dagger engine runs this in a real container, caches each layer, and returns the output.

---

## Pipeline Overview

```
Developer / CI Server
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│  go build -o cert-parser-dagger-go main.go                            │
│  ./cert-parser-dagger-go                                              │
└───────────────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
    Dagger Engine (daemon)          Host machine (for testcontainers)
              │
   ┌──────────┴──────────────────────────────────────────┐
   │                                                     │
   │  Stage 1: Clone repository from GitHub              │
   │  Stage 2: Discover project name from pyproject.toml │
   │  Stage 3: Set up Python 3.14-slim build container   │
   │  Stage 4: pip install framework + project[dev,srv]  │
   │  Stage 5: pytest unit tests (NOT integration)       │  ← inside Dagger
   │  Stage 6: ruff check src/ tests/                    │  ← inside Dagger
   │  Stage 7: mypy src/ --strict                        │  ← inside Dagger
   └─────────────────────────────────────────────────────┘
              │
   ┌──────────┴──────────────────────────────────────────┐
   │  Stage 8: pytest integration tests                  │  ← on HOST machine
   │  Stage 9: pytest acceptance tests                   │  ← on HOST machine
   └─────────────────────────────────────────────────────┘
              │
   ┌──────────┴──────────────────────────────────────────┐
   │  Stage 10: docker build (from repo Dockerfile)      │  ← Dagger builds image
   │  Stage 11: Publish to GHCR (versioned + latest)     │  ← Dagger pushes image
   └─────────────────────────────────────────────────────┘
```

Seven logical stages, numbered 1–7 at runtime (stages are only counted if enabled).

---

## Standard Pipeline (`main.go`)

### Location and Build

```
dagger_go/
├── main.go              ← all pipeline code (572 lines)
├── main_test.go         ← 12 Go unit tests for utility functions
├── go.mod               ← Go 1.24, Dagger SDK v0.19.7
├── run.sh               ← build + run script
└── cert-parser-dagger-go ← compiled binary (gitignored)
```

### Key Data Structure

```go
type Pipeline struct {
    RepoName            string
    ProjectName         string          // auto-discovered from pyproject.toml
    ImageName           string          // Docker-safe image name
    GitRepo             string          // full clone URL
    GitBranch           string
    GitUser             string          // GitHub username
    PipCache            *dagger.CacheVolume
    RunUnitTests        bool
    RunIntegrationTests bool
    RunAcceptanceTests  bool
    RunLint             bool
    RunTypeCheck        bool
    HasDocker           bool            // Docker socket found on host
}
```

### Auto-Discovery: Project Name

Rather than hardcoding `cert-parser`, the pipeline reads `pyproject.toml` from the
cloned repository and extracts:

```
name = "cert-parser"   ← found with regex: (?m)^name\s*=\s*"([^"]+)"
```

This makes the pipeline reusable for other Python projects without code changes.

### Auto-Discovery: Repo Name

The `REPO_NAME` environment variable defaults to the parent directory name:

```bash
REPO_NAME=$(basename "$(cd .. && pwd)")  # e.g. "cert-parser"
```

### Image Tagging

```
ghcr.io/<username>/<image-name>:v0.1.0-<sha7>-<YYYYMMDD-HHMM>
ghcr.io/<username>/<image-name>:latest
```

Example:
```
ghcr.io/johndoe/cert-parser:v0.1.0-a3f8c2d-20260303-1430
ghcr.io/johndoe/cert-parser:latest
```

### Go Quality Gate

The pipeline's own Go code has a quality gate:

```bash
cd dagger_go
go build -o /dev/null .        # compiles without errors
go test -v -run Test           # 12 unit tests all pass
go vet ./...                   # no static analysis warnings
```

Current status: ✅ all green.

---

## Corporate Pipeline (`corporate_main.go`)

For full documentation, see [deployment/CORPORATE_PIPELINE.md](../dagger_go/deployment/CORPORATE_PIPELINE.md).

### Why a Separate File?

The corporate variant is isolated using a Go **build tag**:

```go
//go:build corporate   ← first line of corporate_main.go
```

This means:
- `go build .` → compiles ONLY `main.go` (standard pipeline)
- `go build -tags corporate ...` → compiles ONLY `corporate_main.go`

There is never a "multiple `main` functions" conflict.

### What Corporate Adds

| Feature | Standard | Corporate |
|---------|---------|----------|
| CA certificate mounting | ❌ | ✅ (50+ locations searched) |
| HTTP/HTTPS proxy | ❌ | ✅ |
| Proxy settings in Python container | ❌ | ✅ (`REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`) |
| Certificate diagnostics (`DEBUG_CERTS`) | ❌ | ✅ |
| Windows certificate store paths | ❌ | ✅ |
| Rancher Desktop certificates | ❌ | ✅ |
| Jenkins / GitHub Actions runner certs | ❌ | ✅ |
| Deployment webhook trigger | ❌ | ✅ (`DEPLOY_WEBHOOK`) |
| Host env inheritance for tests | Standard | Same + explicit proxy pass-through |

### When to Use Corporate

Use `run-corporate.sh` when:
- `pip install` or `git clone` fails with "certificate signed by unknown authority"
- Docker pulls fail with TLS errors
- Your organisation uses a MITM proxy

Use `run.sh` (standard) when:
- You are on a personal laptop or home network
- You are running in a clean CI environment with no proxy

---

## Where Tests Run — The Testcontainers Problem

### The Problem

**testcontainers** is our integration/acceptance test framework. It starts a real PostgreSQL
container during each test session. To do this, it needs to:

1. Talk to the Docker daemon via its socket (`/var/run/docker.sock`)
2. Bind-mount a shared volume between the test process and the database container

**Inside a Dagger container**, Docker-in-Docker is used. The Docker socket paths are
remapped, and volume bind-mounts from inside the Dagger container point to directories
that don't exist from the outer Docker daemon's perspective. The result: testcontainers
starts the PostgreSQL container but it can't bind the data volume, and the connection fails.

### The Solution: Host-Based Test Execution

Integration and acceptance tests run directly on the **host machine** using `exec.Command`:

```go
func (p *Pipeline) runTestsOnHost(ctx context.Context, marker string) error {
    // Discover the project root (parent of dagger_go/)
    projectRoot := cwd + "/.."

    // Prefer the project's .venv, fall back to system pytest
    pytestBin := projectRoot + "/.venv/bin/pytest"

    // Run pytest on the host — NOT inside a Dagger container
    cmd := exec.CommandContext(ctx, pytestBin, "-v", "--tb=short", "-m", marker)
    cmd.Dir = projectRoot
    // ...
}
```

The host's Docker daemon is directly available, volume mounts work correctly, and
testcontainers starts PostgreSQL without issues.

### Prerequisite for Host Tests

The project's virtual environment must be installed on the host machine:

```bash
cd cert-parser
python3 -m venv .venv
source .venv/bin/activate
pip install -e "./python_framework"
pip install -e ".[dev,server]"
```

If `.venv` does not exist, the pipeline falls back to the system `pytest` (with a warning).

### Docker Availability Check

Before attempting to run integration or acceptance tests, the pipeline checks whether
Docker is available on the host:

```go
func getDockerSocketPath() string {
    var candidates []string
    switch runtime.GOOS {
    case "windows":
        candidates = []string{`\\.\pipe\docker_engine`, `//./pipe/docker_engine`}
    case "darwin":
        candidates = []string{
            "/var/run/docker.sock",
            os.Getenv("HOME") + "/.docker/run/docker.sock",
            os.Getenv("HOME") + "/.colima/docker.sock",
        }
    default: // linux
        candidates = []string{"/var/run/docker.sock", "/run/docker.sock"}
    }
    // Check each path with os.Stat()
}
```

If Docker is not available, those stages are **skipped** (not failed) with a clear warning.

---

## Running the Pipeline

### Prerequisites

1. **Go 1.24+** — `go version`
2. **Docker** — for integration/acceptance tests and image publishing
3. **GitHub PAT** — `write:packages` scope for GHCR push
4. **Python `.venv`** — for integration/acceptance tests on host

### Standard Pipeline

```bash
cd dagger_go

# Create credentials file
cat > credentials/.env << EOF
CR_PAT=ghp_your_token_here
USERNAME=your_github_username
EOF

# Run (full pipeline)
./run.sh

# Skip slow tests (just unit + lint + type check + build + push)
RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh

# Skip all tests (only lint + build + push)
RUN_UNIT_TESTS=false RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh

# Use a different branch
GIT_BRANCH=feature/my-branch ./run.sh
```

### Corporate Pipeline

```bash
cd dagger_go
mkdir -p credentials/certs

# Add CA certificate
cp /path/to/company-ca.pem credentials/certs/

# Add proxy to credentials/.env
echo "HTTP_PROXY=http://proxy.company.com:8080" >> credentials/.env

# Run
./run-corporate.sh

# With diagnostics
DEBUG_CERTS=true ./run-corporate.sh
```

### Running Go Tests for the Pipeline Itself

```bash
cd dagger_go
go test -v -run Test
# Expected: 12 tests, all PASS in < 1s
```

---

## Configuration Reference

All configuration is via environment variables. All variables are optional except `CR_PAT`
and `USERNAME`.

| Variable | Default | Description |
|----------|---------|-------------|
| `CR_PAT` | — | **Required.** GitHub Personal Access Token (`write:packages`) |
| `USERNAME` | — | **Required.** GitHub username |
| `REPO_NAME` | parent dir name | Repository name (e.g. `cert-parser`) |
| `GIT_BRANCH` | `main` | Branch to clone and build |
| `IMAGE_NAME` | pyproject.toml name | Docker image name (Docker-safe) |
| `RUN_UNIT_TESTS` | `true` | Run pytest unit tests in Dagger container |
| `RUN_INTEGRATION_TESTS` | `true` | Run pytest integration tests on host |
| `RUN_ACCEPTANCE_TESTS` | `true` | Run pytest acceptance tests on host |
| `RUN_LINT` | `true` | Run `ruff check` in Dagger container |
| `RUN_TYPE_CHECK` | `true` | Run `mypy --strict` in Dagger container |
| `HTTP_PROXY` | — | Corporate proxy URL (corporate pipeline only) |
| `HTTPS_PROXY` | — | Corporate proxy URL (corporate pipeline only) |
| `NO_PROXY` | — | Comma-separated proxy bypass list |
| `CA_CERTIFICATES_PATH` | — | Colon-separated extra CA cert paths |
| `DEBUG_CERTS` | `false` | Enable certificate discovery diagnostics |
| `DEPLOY_WEBHOOK` | — | Deployment webhook URL (corporate pipeline only) |

### Bool Parsing

All `RUN_*` flags accept: `true`, `True`, `TRUE`, `1`, `yes`, `Yes`, `YES` (case-insensitive).
Any other value or empty string → uses the default.

---

## Pipeline Internals

### pip Cache

A Dagger cache volume named `pip-cache-<project>` is shared across pipeline runs. This
avoids re-downloading packages on each run. The cache persists as long as the Dagger
engine's state is preserved.

### Layer Caching

Dagger builds containers incrementally. The install sequence:

```go
builder = client.Container().
    From("python:3.14-slim").
    WithExec([]string{"apt-get", "update"}).           // cached
    WithExec([]string{"apt-get", "install", "-y", "git", ...}).   // cached
    WithMountedCache("/root/.cache/pip", p.PipCache).  // persistent cache
    WithMountedDirectory(appWorkdir, source).           // invalidated on code change
    WithExec([]string{"pip", "install", "--upgrade", "pip"}).     // cached
    WithExec([]string{"pip", "install", "-e", "./python_framework"}).  // cached until framework changes
    WithExec([]string{"pip", "install", "-e", ".[dev,server]"})        // cached until pyproject.toml changes
```

Only changing `pyproject.toml` triggers a full pip reinstall. Editing Python code
does NOT trigger pip reinstall because the `COPY` of the source follows the `pip install`.

> **Note**: The source directory is mounted BEFORE pip install so imports are available, but
> the install only re-runs when pyproject.toml changes (tracked by Dagger's content hash).

### Stage Builder Chain

After unit tests pass, the `builder` variable is updated to the test container:
```go
builder = testContainer   // unit tests
builder = lintContainer   // lint
```

This means lint and type check run in the same container state as the tests — no extra
installs, consistent environment.

### Secret Handling

GitHub credentials are passed as Dagger secrets, never logged:

```go
crPAT := client.SetSecret("github-pat", os.Getenv("CR_PAT"))
// Git clone uses crPAT — never printed in logs
repo := client.Git(gitURL, dagger.GitOpts{HTTPAuthToken: crPAT})

password := client.SetSecret("password", os.Getenv("CR_PAT"))
// Registry push uses password — never printed in logs
image.WithRegistryAuth("ghcr.io", p.GitUser, password).Publish(ctx, ...)
```

---

## Build Artifacts

### Pre-Built Binaries

The repository contains pre-built binaries (committed for convenience):

```
dagger_go/cert-parser-dagger-go              ← standard pipeline binary (Linux/amd64)
dagger_go/cert-parser-corporate-dagger-go   ← corporate pipeline binary (Linux/amd64)
```

These are rebuilt by `run.sh` and `run-corporate.sh` on every run (`always rebuild`
pattern). If you are on a different OS/architecture, `go build` compiles for your current
platform automatically.

### Published Docker Image

The pipeline publishes to GitHub Container Registry (GHCR):

```
ghcr.io/<username>/cert-parser:v0.1.0-<sha7>-<YYYYMMDD-HHMM>  ← versioned
ghcr.io/<username>/cert-parser:latest                           ← latest
```

Both tags reference the same image digest. The versioned tag is immutable; `latest`
is overwritten on each successful pipeline run.

---

## Troubleshooting

### "REPO_NAME environment variable is required"

Either set `REPO_NAME=cert-parser` explicitly, or run from inside the `dagger_go/`
directory so that `basename "$(cd .. && pwd)"` resolves to `cert-parser`.

### "Failed to create Dagger client"

The Dagger engine requires Docker. Verify:
```bash
docker info      # must succeed
docker ps        # must not error
```

### Integration tests skipped with "Docker socket NOT available"

On Linux, ensure you are in the `docker` group:
```bash
groups | grep docker     # should include docker
# If missing: sudo usermod -aG docker $USER && newgrp docker
```

On macOS, ensure Docker Desktop or Colima is running:
```bash
docker ps        # test Docker daemon is accessible
```

### "unit tests failed"

The pipeline runs pytest inside the Dagger container. To reproduce locally:
```bash
cd cert-parser
source .venv/bin/activate
pytest -v --tb=short -m "not integration and not acceptance"
```

### Lint / type check failed in pipeline but passes locally

The pipeline clones the repository from GitHub — local uncommitted changes are NOT tested.
Push your changes to the branch first, then re-run the pipeline.

### Corporate pipeline: "certificates not trusted"

See [deployment/CORPORATE_PIPELINE.md](../dagger_go/deployment/CORPORATE_PIPELINE.md) for
the full certificate troubleshooting guide, including how to extract certificates from a
failing TLS connection.

---

## Related Documents

- [deployment/CORPORATE_PIPELINE.md](../dagger_go/deployment/CORPORATE_PIPELINE.md) — corporate proxy setup
- [guides/BUILD_AND_RUN.md](../dagger_go/guides/BUILD_AND_RUN.md) — build & run guide
- [guides/PIPELINE_INTERNALS.md](../dagger_go/guides/PIPELINE_INTERNALS.md) — deep technical details
- [Dockerfile](dockerfile.md) — the production image that the pipeline builds and pushes
- [Testing Strategy](testing-strategy.md) — unit / integration / acceptance test layers
