# Quick Reference: cert-parser Dagger Pipeline

## Run the Pipeline

```bash
cd /path/to/cert-parser/dagger_go

# Full pipeline (all 7 stages)
./run.sh

# Skip integration + acceptance tests (faster)
RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh

# Skip specific stages
RUN_LINT=false ./run.sh
RUN_TYPE_CHECK=false ./run.sh
RUN_UNIT_TESTS=false ./run.sh

# Build binary only (no run)
go build -o cert-parser-dagger-go main.go
```

---

## 7 Pipeline Stages

| # | Stage | Where | Env Var | Default |
|---|-------|--------|---------|---------|
| 1 | Unit Tests | Dagger container | `RUN_UNIT_TESTS` | `true` |
| 2 | Integration Tests | Host machine | `RUN_INTEGRATION_TESTS` | `true` |
| 3 | Acceptance Tests | Host machine | `RUN_ACCEPTANCE_TESTS` | `true` |
| 4 | Lint (ruff) | Dagger container | `RUN_LINT` | `true` |
| 5 | Type Check (mypy) | Dagger container | `RUN_TYPE_CHECK` | `true` |
| 6 | Docker Build | Dagger | always | — |
| 7 | Publish to GHCR | Dagger | always | — |

---

## Credentials Setup

```bash
# Create credentials/.env (gitignored)
cat > dagger_go/credentials/.env << 'EOF'
CR_PAT=ghp_your_github_personal_access_token
USERNAME=your-github-username
EOF
```

Required GitHub PAT scopes: `write:packages`, `read:packages`

---

## Test Markers

```bash
# Run directly without pipeline
cd /path/to/cert-parser

# Unit tests (no Docker needed)
pytest -m "not integration and not acceptance" -v

# Integration tests (needs Docker + testcontainers)
pytest -m integration -v

# Acceptance tests (needs Docker + testcontainers)
pytest -m acceptance -v
```

Integration/acceptance tests use `testcontainers-python` to spin up PostgreSQL automatically.

---

## Docker Socket Detection

The pipeline auto-detects Docker:

| Platform | Socket Path |
|----------|------------|
| Linux | `/var/run/docker.sock` |
| macOS Docker Desktop | `~/.docker/run/docker.sock` |
| macOS Colima | `/var/run/docker.sock.raw` |
| Not found | Tests skipped (not failed) |

---

## Image Tagging

Published images are tagged as:

```
ghcr.io/<USERNAME>/<project>:v0.1.0-<sha7>-<YYYYMMDD-HHMM>
ghcr.io/<USERNAME>/<project>:latest
```

The project name is auto-discovered from `pyproject.toml` → `name = "..."`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CR_PAT not set` | Add to `credentials/.env` |
| Integration tests skip | Start Docker daemon |
| `go: module not found` | Run `go mod tidy` in `dagger_go/` |
| `Permission denied` on `./run.sh` | `chmod +x run.sh test.sh run-corporate.sh` |
| Unit tests fail in container | Check that `python_framework/` is installed before `cert-parser` |
| mypy errors | Run `mypy src/ --strict` locally to reproduce |

---

## Corporate Environment

```bash
# Pipeline with MITM proxy / custom CA support
./run-corporate.sh

# Build the corporate binary
go build -tags corporate -o cert-parser-corporate-dagger-go corporate_main.go
```

---

## Go Pipeline Development

```bash
cd dagger_go

# Build and test the Go pipeline itself
./test.sh

# Run Go unit tests only
go test -v -run Test

# Vet for common issues
go vet ./...

# Format Go code
gofmt -w .
```

---

## Key Files

| File | Purpose |
|------|---------|
| `main.go` | Primary pipeline (7 stages) |
| `corporate_main.go` | Corporate variant (build tag: `corporate`) |
| `run.sh` | Launcher — loads credentials, builds binary, runs pipeline |
| `run-corporate.sh` | Corporate launcher |
| `test.sh` | Build + test the Go pipeline locally |
| `main_test.go` | 12 Go unit tests for pipeline logic |
| `credentials/.env` | `CR_PAT` + `USERNAME` (gitignored, never commit) |
| `go.mod` | `module cert-parser-dagger-go`, Go 1.24, Dagger SDK v0.19.7 |
