# Testcontainers in Dagger Pipeline - Investigation & Solutions

## Problem Statement

Current Dagger pipeline flow:
```
Clone Repository → Run Unit Tests → Build JAR → Dockerize → Publish
```

**Challenges:**
1. ✅ Unit tests can run in Dagger container (no Docker needed)
2. ❌ Integration tests with testcontainers require Docker access
3. ❌ Dagger containers don't have access to Docker daemon by default
4. ❌ Need universal pipeline (works on local dev, CI/CD, different hosts)

**Current Status:**
- Project uses testcontainers (v1.21.3) with PostgreSQL for integration tests
- Dagger pipeline runs inside a container without Docker daemon access
- Pipeline needs to run unit + integration tests before build artifact

---

## Root Cause Analysis

### Why Testcontainers Fails in Dagger Container

**The Issue:**
```
Dagger Container (Alpine/Corretto)
    ↓
Runs Maven Test
    ↓
JUnit discovers testcontainers tests
    ↓
Testcontainers tries to start Docker container
    ↓
ERROR: Cannot connect to Docker daemon (no /var/run/docker.sock)
    ↓
❌ Tests fail, pipeline stops
```

### Why It's Complex

1. **Nested Virtualization:** Container inside container trying to access Docker
2. **Host Docker Access:** Testcontainers needs host machine's Docker daemon
3. **Volume Mounting:** Can't mount `/var/run/docker.sock` in some environments
4. **Portability:** Solution must work on:
   - Local developer machine (Docker Desktop)
   - GitHub Actions (Docker available)
   - GitLab CI (Docker available)
   - Self-hosted runners (may not have Docker)

---

## Solution Approaches

### ✅ SOLUTION 1: Docker-in-Docker (DinD) with Dagger

**How it works:**
```
Host Docker Daemon
    ↓
Dagger Container (privileged)
    ↓
Docker daemon inside container
    ↓
Maven runs testcontainers
    ↓
Testcontainers starts PostgreSQL container
```

**Implementation:**
```go
// In dagger_go/main.go - within the run() function

// Create privileged container with Docker daemon
const (
    baseImage = "docker:dind"  // Docker-in-Docker image
    javaImage = "amazoncorretto:25.0.1"
)

// Stage 0: DinD sidecar for testcontainers
fmt.Println("🐳 Starting Docker-in-Docker sidecar...")
dindService := client.Container().
    From(baseImage).
    WithEnvVariable("DOCKER_TLS_CERTDIR", "")  // Disable TLS for simplicity

// This would require special orchestration - see limitations below

// Stage 1: Build container with Maven + Docker client
builder := client.Container().
    From(javaImage).
    WithExec([]string{"yum", "install", "-y", "maven", "git", "docker"}).
    WithMountedCache("/root/.m2", p.MavenCache)

// Connect to DinD socket
// .WithUnixSocket("/var/run/docker.sock", dindService.Socket("/var/run/docker.sock"))
```

**Advantages:**
- ✅ Full Docker capabilities within pipeline
- ✅ Testcontainers works natively
- ✅ Integration tests run completely

**Disadvantages:**
- ❌ Dagger Go SDK has limited service orchestration support
- ❌ Requires privileged containers (security concern)
- ❌ Complex setup with multiple containers
- ❌ Additional latency (container startup overhead)
- ❌ Not all CI/CD platforms allow privileged containers

**Best for:** GitHub Actions, GitLab CI with relaxed security policies

---

### ✅ SOLUTION 2: Use Docker Host Socket Binding (Recommended)

**How it works:**
```
Host Machine
    ├─ Docker Daemon (/var/run/docker.sock)
    │
    └─ Dagger Client (local)
         ↓
         Dagger Container (mounted socket)
            ↓
            Testcontainers connects to host Docker
            ↓
            PostgreSQL container started on host
```

**Implementation:**
```go
// In dagger_go/main.go

func (p *RailwayPipeline) run(ctx context.Context, client *dagger.Client) error {
    const baseImage = "amazoncorretto:25.0.1"

    p.MavenCache = client.CacheVolume("maven-cache")

    // Clone repository (same as before)
    repo := client.Git(gitURL, dagger.GitOpts{...})
    source := repo.Branch(p.GitBranch).Tree()

    // Setup builder
    builder := client.Container().
        From(baseImage).
        WithExec([]string{"yum", "install", "-y", "maven", "git", "docker"}).
        WithMountedCache("/root/.m2", p.MavenCache).
        WithMountedDirectory("/app", source).
        WithWorkdir("/app/railway_framework")

    // ✅ KEY CHANGE: Mount host Docker socket
    if dockerSocket := os.Getenv("DOCKER_HOST"); dockerSocket != "" {
        // Custom Docker socket path
        builder = builder.WithUnixSocket(dockerSocket,
            client.UnixSocket(dockerSocket))
    } else {
        // Default Docker socket on Unix-like systems
        builder = builder.WithUnixSocket("/var/run/docker.sock",
            client.UnixSocket("/var/run/docker.sock"))
    }

    // Stage 1: Run unit + integration tests
    fmt.Println("🧪 Running unit and integration tests...")
    testContainer := builder.WithExec([]string{
        "mvn", "test",  // Runs ALL tests (unit + integration)
        "-Dmaven.compiler.release=25",
        "-Dmaven.compiler.compilerArgs=--enable-preview",
        "-q",
    })

    _, err = testContainer.Stdout(ctx)
    if err != nil {
        fmt.Printf("❌ Tests failed\n")
        return fmt.Errorf("tests failed: %w", err)
    }
    fmt.Println("✅ All tests passed (unit + integration)")

    // Stage 2: Build JAR
    fmt.Println("📦 Building Maven artifact...")
    // ... rest of build continues
}
```

**Advantages:**
- ✅ Simplest implementation
- ✅ Testcontainers works natively without modification
- ✅ Works on local development machines
- ✅ Works on CI/CD with Docker support
- ✅ No privileged containers needed
- ✅ No Docker-in-Docker overhead
- ✅ Single container orchestration

**Disadvantages:**
- ❌ Requires Docker daemon on host machine
- ❌ Won't work on systems without Docker (e.g., Kubernetes-only)
- ❌ `/var/run/docker.sock` socket permissions must be correct
- ❌ Security: container gets host Docker access

**Best for:** Development machines, GitHub Actions, GitLab CI

---

### ✅ SOLUTION 3: Separate Test Stage (Integration Tests in Docker)

**How it works:**
```
Dagger Pipeline Stage 1: Unit Tests (no Docker needed)
    ↓ (pass/fail)
Dagger Pipeline Stage 2: Integration Tests (run in docker-compose)
    ↓ (pass/fail)
Dagger Pipeline Stage 3: Build artifact
```

**Implementation:**
```go
func (p *RailwayPipeline) run(ctx context.Context, client *dagger.Client) error {
    // ... setup code ...

    // Stage 1: Run ONLY unit tests (fast, no Docker)
    fmt.Println("🧪 Running unit tests...")
    unitTestContainer := builder.WithExec([]string{
        "mvn", "test",
        "-DexcludedGroups=integration",  // Exclude integration tests
        "-Dmaven.compiler.release=25",
        "-q",
    })

    _, err = unitTestContainer.Stdout(ctx)
    if err != nil {
        return fmt.Errorf("unit tests failed: %w", err)
    }
    fmt.Println("✅ Unit tests passed")

    // Stage 2: Run integration tests OUTSIDE Dagger (in docker-compose)
    fmt.Println("🧪 Running integration tests...")

    // Option A: External docker-compose execution
    integrationTestCmd := builder.WithExec([]string{
        "sh", "-c",
        `cd /app/deployment/docker-compose && \
         docker-compose -f docker-compose.dev.yml up -d && \
         sleep 30 && \
         cd /app/railway_framework && \
         mvn test -Dgroups=integration -q && \
         RESULT=$? && \
         cd /app/deployment/docker-compose && \
         docker-compose -f docker-compose.dev.yml down && \
         exit $RESULT`,
    })

    _, err = integrationTestCmd.Stdout(ctx)
    if err != nil {
        return fmt.Errorf("integration tests failed: %w", err)
    }
    fmt.Println("✅ Integration tests passed")

    // Stage 3: Build
    fmt.Println("📦 Building artifact...")
    // ... build continues
}
```

**Advantages:**
- ✅ Clean separation of concerns
- ✅ Unit tests run fast (no Docker)
- ✅ Integration tests get full Docker environment
- ✅ Can skip integration tests with flag if needed
- ✅ Failure attribution clear (unit vs integration)

**Disadvantages:**
- ❌ Still requires Docker daemon on host
- ❌ More complex orchestration
- ❌ Longer build time (separate test stages)
- ❌ Need to mark tests with @Tag("integration")

**Best for:** Large projects with many unit tests, selective testing

---

### ✅ SOLUTION 4: Conditional Test Execution (Recommended for CI/CD)

**How it works:**
```
Environment Detection
    ↓
If Docker available → Run full tests (unit + integration)
If Docker NOT available → Run unit tests only, skip integration
    ↓
Build artifact regardless
```

**Implementation:**
```go
func (p *RailwayPipeline) run(ctx context.Context, client *dagger.Client) error {
    // ... setup ...

    // Detect if Docker is available
    hasDocker := hasDockerAccess(ctx, builder)

    var testArgs []string
    if hasDocker {
        fmt.Println("✅ Docker detected - running full test suite (unit + integration)")
        testArgs = []string{"mvn", "test", "-q"}
    } else {
        fmt.Println("⚠️  Docker NOT available - running unit tests only")
        testArgs = []string{"mvn", "test", "-DexcludedGroups=integration", "-q"}
    }

    testContainer := builder.WithExec(testArgs)
    _, err = testContainer.Stdout(ctx)
    if err != nil {
        return fmt.Errorf("tests failed: %w", err)
    }

    fmt.Println("✅ Tests completed successfully")

    // Build continues
}

func hasDockerAccess(ctx context.Context, container *dagger.Container) bool {
    // Try to check if docker socket exists
    _, err := container.WithExec([]string{
        "test", "-e", "/var/run/docker.sock",
    }).Stdout(ctx)
    return err == nil
}
```

**Advantages:**
- ✅ Works everywhere (Docker or not)
- ✅ Best effort testing
- ✅ Simple implementation
- ✅ Progressive quality gates

**Disadvantages:**
- ❌ Different test coverage in different environments
- ❌ May miss integration bugs
- ❌ Unpredictable quality standards

**Best for:** Open source projects, multiple deployment targets

---

### ⚠️ SOLUTION 5: TestcontainersException Handling

**How it works:**
```
Setup Testcontainers
    ↓
Try to create container
    ↓
If fails (no Docker) → Fall back to embedded/test database
    ↓
Continue with limited testing
```

**In Java code:**
```java
@SpringBootTest
class CatalogRepositoryImplIntegrationTest {

    // Skip test if testcontainers unavailable
    @Testcontainers
    static class IntegrationTestConfig {
        static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>(
            DockerImageName.parse("postgres:16-alpine")
        ).withDatabaseName("railway_test");

        @DynamicPropertySource
        static void configureProperties(DynamicPropertyRegistry registry) {
            if (postgres.isRunning()) {
                registry.add("spring.datasource.url", postgres::getJdbcUrl);
                registry.add("spring.datasource.username", postgres::getUsername);
                registry.add("spring.datasource.password", postgres::getPassword);
            } else {
                // Fallback to H2 in-memory database
                registry.add("spring.datasource.driver-class-name",
                    () -> "org.h2.Driver");
                registry.add("spring.datasource.url",
                    () -> "jdbc:h2:mem:testdb");
            }
        }
    }
}
```

**Advantages:**
- ✅ Graceful degradation
- ✅ Tests still run (limited scope)
- ✅ No test failures on missing Docker

**Disadvantages:**
- ❌ Silently reduced test coverage
- ❌ May not catch real issues
- ❌ Hidden quality degradation

**Best for:** Development environments with fallback testing

---

## Recommended Solution Path

### Phase 1: Immediate (SOLUTION 2 + 4)
**Use Docker Socket Binding + Conditional Testing**

```go
// Enhanced main.go
const (
    baseImage = "amazoncorretto:25.0.1"
)

func (p *RailwayPipeline) run(ctx context.Context, client *dagger.Client) error {
    // Mount Docker socket for testcontainers
    builder := setupBuilder(client, baseImage)

    // Check Docker availability
    hasDocker := checkDockerAvailable(ctx, builder)

    // Run tests (full if Docker, unit-only if not)
    testContainer := runTests(ctx, builder, hasDocker)

    // Build and publish
    return buildAndPublish(ctx, testContainer, p)
}
```

**Setup script changes:**
```bash
#!/bin/bash
# dagger_go/run.sh - Enhanced for testcontainers

set -a
source ${workspaceFolder}/credentials/.env
set +a

# Ensure Docker is available
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker not found - integration tests will be skipped"
fi

cd ${workspaceFolder}/dagger_go

# For Linux/Mac with Docker
if [ -S /var/run/docker.sock ]; then
    echo "✅ Docker socket available at /var/run/docker.sock"
    export DOCKER_HOST="unix:///var/run/docker.sock"
fi

# Run Dagger pipeline
go run main.go
```

### Phase 2: Enhanced (SOLUTION 3)
**Separate test stages with explicit categorization**

```java
// Mark tests
@Tag("integration")
class CatalogRepositoryImplIntegrationTest { ... }

@Tag("unit")
class UpdateOrderStagesTest { ... }
```

```go
// Run with Maven profiles
"-DexcludedGroups=integration"  // Unit tests only
// or
"-Dgroups=integration"  // Integration tests only
```

### Phase 3: Advanced (SOLUTION 1)
**Docker-in-Docker for maximum portability** (future, if needed)

Only if your CI/CD platform (Kubernetes, restricted environments) requires it.

---

## Environment Configuration

### Local Development (Mac/Linux with Docker Desktop)

```bash
# Automatic detection - just ensure Docker is running
docker ps  # Verify Docker daemon is accessible

cd dagger_go
go run main.go
```

### CI/CD Platforms

**GitHub Actions:**
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Dagger Pipeline
        run: |
          cd dagger_go
          go run main.go
          # Docker socket automatically available
```

**GitLab CI:**
```yaml
build-pipeline:
  image: golang:1.22
  services:
    - docker:dind  # Enable Docker-in-Docker
  variables:
    DOCKER_HOST: unix:///var/run/docker.sock
  script:
    - cd dagger_go
    - go run main.go
```

**Self-Hosted Runner (Linux):**
```bash
# Install Docker on runner
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Ensure socket permissions
sudo usermod -aG docker $USER
newgrp docker

# Run pipeline
cd dagger_go
go run main.go
```

---

## Implementation Checklist

- [ ] **Phase 1: Docker Socket Binding**
  - [ ] Update `main.go` to detect and mount Docker socket
  - [ ] Add Docker client installation to builder image
  - [ ] Update test stage to check Docker availability
  - [ ] Test locally with Docker Desktop
  - [ ] Test on GitHub Actions

- [ ] **Phase 2: Test Categorization** (Optional)
  - [ ] Add `@Tag("integration")` to integration tests
  - [ ] Add `@Tag("unit")` to unit tests
  - [ ] Create Maven profiles for selective testing
  - [ ] Add `--help` flag to main.go for test selection

- [ ] **Phase 3: Docker-in-Docker** (Future)
  - [ ] Create DinD orchestration helper
  - [ ] Test on Kubernetes/restricted environments
  - [ ] Document privilege requirements

---

## Testing the Solution

```bash
# Test 1: Local with Docker
cd dagger_go
go run main.go  # Should run all tests

# Test 2: Docker socket availability
docker ps  # Verify access

# Test 3: Testcontainers specifically
mvn test -Dgroups=integration  # Run only integration tests

# Test 4: Without Docker (simulate)
sudo systemctl stop docker  # Stop Docker daemon
go run main.go  # Should fail gracefully or skip integration

# Test 5: GitHub Actions
git push  # Trigger workflow - verify pipeline succeeds
```

---

## References

- **Testcontainers Go Module:** https://testcontainers.com/
- **Dagger SDK:** https://dagger.io/sdk/go
- **Docker Socket Security:** https://docs.docker.com/engine/security/
- **CI/CD Docker Support:**
  - GitHub Actions: https://docs.github.com/en/actions/using-github-hosted-runners
  - GitLab CI: https://docs.gitlab.com/ee/ci/docker/
  - Jenkins: https://www.jenkins.io/doc/book/managing/jenkins-with-docker/

---

## Questions & Answers

**Q: Will testcontainers work with Podman instead of Docker?**
A: Yes, with modifications. Set `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/podman/podman.sock`

**Q: Can we run testcontainers in Kubernetes directly?**
A: Not directly. You'd need DinD or privileged containers. Use embedded databases or mock services instead.

**Q: What about Windows developers?**
A: Windows 10+ with WSL 2 has `/var/run/docker.sock` available through the Docker Desktop integration.

**Q: How does this affect build times?**
A: Minimal. Docker socket mounting is instant. Testcontainers container startup adds ~10-30s per test suite.

**Q: Is mounting `/var/run/docker.sock` a security risk?**
A: Yes - container can access any Docker image/container on host. Acceptable for CI/CD, use caution for untrusted workloads.

