# Dagger Go Build & Run Guide

Complete guide to building and running the Railway-Oriented Java Dagger Go CI/CD pipeline.

## ⚡ Quick Reference

| Goal | Command | Time |
|------|---------|------|
| **Unit tests only** | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_INTEGRATION_TESTS=false ./run.sh` | 5-10s |
| **Full pipeline** | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=true RUN_INTEGRATION_TESTS=true ./run.sh` | 40-60s |
| **Corporate pipeline** | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME DEBUG_CERTS && ./run-corporate.sh` | 40-60s |
| **Integration only** | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=false ./run.sh` | 30-45s |
| **Default (smart)** | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && ./run.sh` | 40-60s |
| **Test code** | `cd dagger_go && set -a && source ../credentials/.env && set +a && go test -v` | 30-60s |
| **Build binary** | `cd dagger_go && go build -o railway-dagger-go main.go` | 5-10s |
| **Build corporate** | `cd dagger_go && go build -o railway-corporate-dagger-go corporate_main.go` | 5-10s |
| **Debug** | VSC F5 → Debug Dagger Go | Live |

**Key Points**:
- ❌ **Dagger CLI NOT required** - Uses Dagger Go SDK
- ✅ **Docker required** for integration tests (optional for unit tests)
- ✅ **Environment variables** control test scope
- ✅ **Smart defaults** - full coverage by default, graceful degradation without Docker

---

## Prerequisites

### What You Need

```bash
✅ Go 1.22+
✅ Docker running
✅ credentials/.env with CR_PAT and USERNAME
❌ Dagger CLI (NOT needed - SDK handles it)
```

### Verify Setup

```bash
go version                  # Should show go1.22+
docker ps                   # Should work
cat credentials/.env        # Should show CR_PAT=... USERNAME=...
```

---

## Workflows

### Workflow 1: Test Code

**Goal**: Verify code compiles and tests pass

**Command:**

```bash
cd dagger_go
set -a && source ../credentials/.env && set +a && go test -v
```

**What happens:**
1. Loads CR_PAT and USERNAME from credentials/.env
2. Downloads Dagger Go SDK v0.19.7 (automatically)
3. Runs unit tests

**Success output:**
```
go: downloading dagger.io/dagger v0.19.7
--- PASS: TestProjectRootDiscovery (1.234s)
--- PASS: TestEnvironmentVariables (0.567s)
PASS
ok      railway/dagger    2.345s
```

**Duration**: 30-60 seconds (first time), 5-10 seconds (cached)

**Key Notes:**
- ✅ Uses Dagger Go SDK (downloads automatically)
- ❌ Does NOT require Dagger CLI installed
- Requires Docker running (SDK uses Docker Engine)

---

### Workflow 2: Build Binary

**Goal**: Create executable for deployment

**Command:**

```bash
cd dagger_go
go mod download dagger.io/dagger && go mod tidy
go build -o railway-dagger-go main.go
```

**What happens:**
1. Downloads Dagger Go SDK and all dependencies
2. Compiles Go code to standalone executable
3. Creates 20MB binary: `railway-dagger-go`

**Success output:**
```
$ ls -lh railway-dagger-go
-rwxrwxr-x 20M railway-dagger-go
$ file railway-dagger-go
railway-dagger-go: ELF 64-bit LSB executable, x86-64
```

**Duration**: 5-10 seconds

**Key Notes:**
- ✅ Pure Go compilation (no dependencies needed after download)
- ❌ Does NOT require Docker
- Binary ready for server deployment
- Run with credentials: `set -a && source ../credentials/.env && set +a && ./railway-dagger-go`

---

### Workflow 3: Run Pipeline with Independent Test Control

**Goal**: Run the pipeline with flexible test scoping

**Key Feature**: Choose which tests to run via environment variables:

```bash
# Full suite (unit + integration tests)
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=true RUN_INTEGRATION_TESTS=true ./run.sh

# Unit tests only (fast: 5-10 seconds, no Docker required)
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_INTEGRATION_TESTS=false ./run.sh

# Integration tests only (30-45 seconds, requires Docker)
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=false ./run.sh

# Default (full suite with smart Docker detection)
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && ./run.sh
```

**Test Matrix:**

| Scenario | Command | Tests | Time | Docker |
|----------|---------|-------|------|--------|
| Full (default) | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=true RUN_INTEGRATION_TESTS=true ./run.sh` | Unit + Integration | 40-60s | Optional |
| Unit only | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_INTEGRATION_TESTS=false ./run.sh` | Unit | 5-10s | No |
| Integration | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=false ./run.sh` | Integration | 30-45s | Yes |
| Auto-degrade | `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && ./run.sh` (no Docker) | Unit | 5-10s | No |

**How it works:**

1. Pipeline checks `RUN_UNIT_TESTS` and `RUN_INTEGRATION_TESTS` environment variables
2. Detects Docker availability automatically
3. Runs appropriate test scope:
   - **Both true + Docker available** → Full suite (unit + integration with testcontainers)
   - **Unit true, Integration false** → Unit tests only (fast)
   - **Unit false, Integration true + Docker** → Integration tests only (focused)
   - **Docker unavailable** → Gracefully runs unit tests only
4. Logs configuration at startup for visibility

**Console Output Example:**

```
🧪 Test Configuration:
   Unit tests: true (override with RUN_UNIT_TESTS=false)
   Integration tests: true (override with RUN_INTEGRATION_TESTS=false)

🔍 Checking Docker availability for testcontainers...
✅ Docker detected - mounting Docker socket for full test suite

🧪 Running tests...
   📊 Test scope: Unit + Integration (with Docker)
✅ Tests passed successfully
```

**GitHub Actions Integration:**

Fast PR checks:
```yaml
- name: Quick Unit Tests
  env:
    RUN_INTEGRATION_TESTS: 'false'
    CR_PAT: ${{ secrets.CR_PAT }}
    USERNAME: ${{ github.actor }}
  run: cd dagger_go && ./run.sh
```

Full tests on main:
```yaml
- name: Full Test Suite
  env:
    CR_PAT: ${{ secrets.CR_PAT }}
    USERNAME: ${{ github.actor }}
  run: cd dagger_go && ./run.sh
```

**Key Points:**
- ✅ Environment-variable driven (easy to configure)
- ✅ Smart defaults (full coverage by default)
- ✅ Graceful degradation (works without Docker)
- ✅ Fast feedback (unit-only in 5-10 seconds)
- ✅ Flexible CI/CD (different workflows for different needs)

---

### Workflow 4: Run Full CI/CD Pipeline

**Goal**: Build Docker image and deploy to GitHub Container Registry

**Command:**

```bash
cd dagger_go
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && ./run.sh
```

**What happens:**
1. Loads credentials from credentials/.env
2. Connects to Dagger Engine (via Docker)
3. Builds Maven project (`mvn clean package`)
4. Creates Docker image
5. Tags with git commit SHA
6. Pushes to GitHub Container Registry

**Success output:**
```
🚀 Starting Railway Dagger Go CI/CD Pipeline...
📦 Building Maven project...
  [INFO] BUILD SUCCESS
🐳 Building Docker image...
  Step 1/15 : FROM amazoncorretto:25.0.1-al2
  ...
📤 Pushing to GHCR...
  Digest: sha256:abc123def456...
✅ Pipeline completed successfully!
Image: ghcr.io/username/railway_framework:abc1234def
```

**Duration**:
- First run: 3-5 minutes (downloads dependencies)
- Cached run: 1-2 minutes (uses layer cache)

**Requirements:**
- ✅ Docker running (Dagger SDK uses it)
- ✅ CR_PAT and USERNAME in credentials/.env
- ❌ Dagger CLI NOT required

---

### Workflow 5: Run Corporate Pipeline (MITM Proxy + CA Certificates)

**Goal**: Build with corporate proxy and custom CA certificates support

**Command:**

```bash
cd dagger_go
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME DEBUG_CERTS && ./run-corporate.sh
```

**What's Different:**
- Auto-discovers CA certificates from 50+ locations
- Supports corporate MITM proxies (HTTP_PROXY, HTTPS_PROXY)
- Mounts certificates into containers automatically
- Enhanced logging with `DEBUG_CERTS=true`

**Prerequisites:**

1. **Place CA certificates** (optional):
   ```bash
   mkdir -p credentials/certs
   cp /path/to/corporate-ca.pem credentials/certs/
   ```

2. **Configure proxy** (optional - add to `credentials/.env`):
   ```bash
   HTTP_PROXY=http://proxy.company.com:8080
   HTTPS_PROXY=https://proxy.company.com:8080
   ```

3. **Enable debug logging** (optional):
   ```bash
   DEBUG_CERTS=true
   ```

**Success output:**
```
🏢 CORPORATE MODE: MITM Proxy & Custom CA Support
   🔍 Debug mode: ENABLED - Certificate discovery active
   📜 Found 2 CA certificate path(s)
      - ca-certificates.crt ✅
      - certs ✅

📜 Certificate Discovery - Detailed Log
─────────────────────────────────────────────────────────────────────────────────
🔍 Source: User-provided certificates (credentials/certs/)
   ✅ Found: credentials/certs/corporate-ca.pem

🔍 Source: System certificate stores (50+ locations)
   ✅ Found: /etc/ssl/certs/ca-certificates.crt

📊 Certificate Discovery Summary
─────────────────────────────────────────────────────────────────────────────────
   🔍 Total sources checked: 37
   ✅ Certificates found: 2
   ℹ️  Not found: 35
   📜 Unique certificates collected: 2
─────────────────────────────────────────────────────────────────────────────────

🚀 Starting Railway Dagger Go CI/CD Pipeline...
📦 Building Maven project...
✅ Pipeline completed successfully!
```

**Certificate Auto-Discovery Sources:**
1. `credentials/certs/` (user-provided `.pem` files)
2. System stores (`/etc/ssl/certs/`, `/etc/pki/ca-trust/`)
3. Docker/Rancher Desktop directories (`.docker/certs.d`, `.rancher/certs.d`)
4. macOS Docker Desktop Group Containers
5. Windows Certificate Store (via WSL)
6. Jenkins CI/CD environment (`$JENKINS_HOME/certs`)
7. GitHub Actions runner (`$RUNNER_TEMP/ca-certificates`)
8. `CA_CERTIFICATES_PATH` environment variable

**Documentation:**
- [CERTIFICATE_LOGGING.md](../CERTIFICATE_LOGGING.md) - Detailed logging guide
- [CERTIFICATE_QUICK_REFERENCE.md](../CERTIFICATE_QUICK_REFERENCE.md) - Setup guide
- [.github/instructions/dagger-certificate-implementation.instructions.md](../../.github/instructions/dagger-certificate-implementation.instructions.md) - Technical details

**Duration**: 40-60 seconds (same as standard pipeline)

**Key Notes:**
- ✅ Gracefully degrades if no certificates found
- ✅ Works on Linux, macOS, Windows (WSL), Jenkins, GitHub Actions
- ✅ Zero configuration needed (auto-discovery works automatically)
- ✅ Optional manual configuration via `credentials/certs/`

---

## Debug Your Code (VSC)

### Setup

1. Open workspace: `code .vscode/railway.code-workspace`
2. Open `dagger_go/main.go`
3. Click gutter (left margin) next to line number to set breakpoint
4. Red circle ⭕ appears

### Run Debugger

Press `F5` and select "Debug Dagger Go"

**Debug Controls:**

| Key | Action |
|-----|--------|
| F10 | Step over |
| F11 | Step into |
| Shift+F11 | Step out |
| F5 | Continue |
| Shift+F5 | Stop |

**Inspect Variables:**
- Left panel shows locals, watch expressions, call stack
- Hover over variables to inspect values

---

## File Structure

```
railway_oriented_java/
├── credentials/
│   └── .env                    # CR_PAT, USERNAME (your secrets)
│
├── dagger_go/                  # ← You work here
│   ├── main.go                 # Pipeline code (230+ lines)
│   ├── main_test.go            # Unit tests
│   ├── go.mod                  # Go module definition
│   ├── go.sum                  # Dependency checksums
│   ├── test.sh                 # Test runner
│   ├── run.sh                  # Pipeline executor
│   ├── railway-dagger-go       # Binary (after `go build`)
│   └── BUILD_AND_RUN.md        # This file
│
├── .vscode/
│   ├── tasks.json              # VSC tasks (for reference)
│   ├── launch.json             # Debug config
│   ├── settings.json           # Editor settings
│   └── railway.code-workspace  # Multi-folder workspace
│
├── railway_framework/          # Main Java application
│   ├── pom.xml
│   └── src/
│
└── deployment/                 # Kubernetes configs
    └── k8s/
```

---

## Troubleshooting

### Error: "dagger: command not found"

**Cause**: You tried to use Dagger CLI

**Solution**: Don't use Dagger CLI! Use Go commands instead:

```bash
# ❌ Wrong:
dagger run

# ✅ Right:
cd dagger_go
go test -v
./run.sh
```

The Dagger Go SDK in `go.mod` handles everything.

### Error: "Cannot connect to Docker daemon"

**Cause**: Docker not running

**Solution**:

```bash
docker ps
# If error:
# - macOS/Windows: Open Docker Desktop app
# - Linux: sudo systemctl start docker
```

### Error: "credentials/.env not found"

**Cause**: Missing credentials file

**Solution**:

```bash
cat > credentials/.env << EOF
CR_PAT=ghp_your_github_token
USERNAME=your_github_username
EOF
```

### Error: "go: command not found"

**Cause**: Go not in PATH

**Solution**:

```bash
which go
# Should show: /usr/local/go/bin/go

# Add to PATH if needed:
export PATH=$PATH:/usr/local/go/bin
```

### Error: "Permission denied: ./run.sh"

**Cause**: Script doesn't have execute permissions

**Solution**:

```bash
chmod +x dagger_go/run.sh
chmod +x dagger_go/test.sh

# Try again
cd dagger_go
set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && ./run.sh
```

### Error: "No such file or directory: ./run.sh"

**Cause**: Script not executable

**Solution**:

```bash
chmod +x dagger_go/test.sh
chmod +x dagger_go/run.sh
```

### Error: "go: unknown module: dagger.io/dagger"

**Cause**: Dependencies not downloaded

**Solution**:

```bash
cd dagger_go
go mod download dagger.io/dagger
go mod tidy
go test -v
```

### Error: "missing go.sum entry for module providing package dagger.io/dagger"

**Cause**: go.sum file not synchronized with go.mod

**Solution** (run these in order):

```bash
cd dagger_go

# Step 1: Download the Dagger module
go mod download dagger.io/dagger

# Step 2: Tidy up go.mod and go.sum
go mod tidy

# Step 3: Try building again
go build -o railway-dagger-go main.go
```

**Expected output:**
```
go: downloading dagger.io/dagger v0.19.7
go: downloading github.com/Khan/genqlient v0.8.1
[... more downloads ...]
```

After these commands complete, `go.sum` will be updated and the build will succeed.

---

## Common Issues & Quick Fixes

| Problem | Quick Fix |
|---------|-----------|
| "Command not found: go" | Install Go from golang.org |
| "Cannot connect to Docker" | Start Docker Desktop or daemon |
| "Permission denied: ./run.sh" | `chmod +x dagger_go/test.sh run.sh` |
| ".env not found" | Create `credentials/.env` with CR_PAT and USERNAME |
| "Module not found" | `cd dagger_go && go mod tidy` |
| "dagger: command not found" | Don't use Dagger CLI - use `go test -v` instead |

---

## Performance Tips

### Faster Builds

1. **Keep Docker running** - Reuses containers
2. **Run tests only** - `go test -v` (faster than full pipeline)
3. **Use layer cache** - Docker caches previous layers

### Faster Development

1. **Build once** - `go build -o railway-dagger-go main.go`
2. **Deploy binary** - Run binary on servers
3. **Debug locally** - F5 for breakpoints

---

## Next Steps

1. ✅ Verify prerequisites (Go, Docker, credentials/.env)
2. ✅ Test code: `cd dagger_go && set -a && source ../credentials/.env && set +a && go test -v`
3. ✅ Build binary: `cd dagger_go && go mod download dagger.io/dagger && go build -o railway-dagger-go main.go`
4. ✅ Run pipeline: `set -a && source ../credentials/.env && set +a && export CR_PAT USERNAME && RUN_UNIT_TESTS=true RUN_INTEGRATION_TESTS=true ./run.sh`
5. ✅ Monitor logs in Dagger Cloud (link provided in output)
6. ✅ Check image in GitHub Container Registry

---

## Resources

- 📖 [Go Documentation](https://golang.org/doc)
- 🐳 [Docker Documentation](https://docs.docker.com)
- 🔧 [Dagger SDK](https://docs.dagger.io)
- ⚡ [Quick Start Guide](./QUICKSTART.md)
- 📋 [Dagger Go SDK Docs](./DAGGER_GO_SDK.md)

---

**Summary**: No Dagger CLI needed. Just Go + Docker. Run `go test -v` to verify, `go build` to create binary, `./run.sh` to deploy. All credentials loaded from `credentials/.env` automatically.

**Last Updated**: November 22, 2025
**Status**: ✅ Ready to use
