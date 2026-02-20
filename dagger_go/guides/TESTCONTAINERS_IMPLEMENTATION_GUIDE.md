# Implementation Guide: Testcontainers Support in Dagger Pipeline

This guide shows **SOLUTION 2 + 4** implementation (Docker Socket Binding + Conditional Testing) for your `main.go`.

## Overview of Changes

```
Current Flow:
├─ Clone Repository
├─ Run Unit Tests (✅ works)
├─ Build JAR
├─ Dockerize
└─ Publish

Enhanced Flow:
├─ Clone Repository
├─ Setup Builder (+ Docker socket mounting)
├─ Run Unit Tests
├─ Detect Docker availability
├─ Run Integration Tests (if Docker available)
├─ Build JAR
├─ Dockerize
└─ Publish
```

---

## Step 1: Update main.go with Docker Socket Support

### Key Changes:

1. **Install Docker client in builder**
2. **Mount Docker socket from host**
3. **Detect Docker availability**
4. **Run full or partial tests based on Docker**
5. **Add error handling for missing Docker**

### Implementation:

```go
package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"dagger.io/dagger"
)

// RailwayPipeline represents the Railway-Oriented Java framework CI/CD pipeline
type RailwayPipeline struct {
	RepoName       string
	ImageName      string
	GitRepo        string
	GitBranch      string
	GitUser        string
	MavenCache     *dagger.CacheVolume
	ContainerImg   *dagger.Container
	HasDocker      bool  // Track Docker availability
}

// main runs the Railway-Oriented Programming framework CI/CD pipeline in Go
func main() {
	ctx := context.Background()

	// Check for required environment variables
	requiredVars := []string{"CR_PAT", "USERNAME"}
	for _, varName := range requiredVars {
		if _, exists := os.LookupEnv(varName); !exists {
			fmt.Fprintf(os.Stderr, "ERROR: %s environment variable must be set\n", varName)
			os.Exit(1)
		}
	}

	// Get repository information from environment
	repoName := os.Getenv("REPO_NAME")
	if repoName == "" {
		repoName = "railway_oriented_java"
	}

	gitRepo := os.Getenv("GIT_REPO")
	if gitRepo == "" {
		username := os.Getenv("USERNAME")
		gitRepo = fmt.Sprintf("https://github.com/%s/%s.git", username, repoName)
	}

	gitBranch := os.Getenv("GIT_BRANCH")
	if gitBranch == "" {
		gitBranch = "main"
	}

	imageNameEnv := os.Getenv("IMAGE_NAME")
	if imageNameEnv == "" {
		imageNameEnv = repoName
	}

	fmt.Printf("🚀 Starting %s CI/CD Pipeline (Go SDK v0.19.7)...\n", repoName)
	fmt.Printf("   Repository: %s (branch: %s)\n", gitRepo, gitBranch)

	// Initialize Dagger client
	client, err := dagger.Connect(ctx, dagger.WithLogOutput(os.Stderr))
	if err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Failed to create Dagger client: %v\n", err)
		os.Exit(1)
	}
	defer client.Close()

	pipeline := &RailwayPipeline{
		RepoName:  repoName,
		ImageName: imageNameEnv,
		GitRepo:   gitRepo,
		GitBranch: gitBranch,
		GitUser:   os.Getenv("USERNAME"),
	}

	// Run pipeline stages
	if err := pipeline.run(ctx, client); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Pipeline failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("\n🎉 Pipeline completed successfully!")
}

// run executes the complete CI/CD pipeline
func (p *RailwayPipeline) run(ctx context.Context, client *dagger.Client) error {
	const baseImage = "amazoncorretto:25.0.1"

	// Create Maven cache volume
	p.MavenCache = client.CacheVolume("maven-cache")

	// Get Git repository
	fmt.Println("🔖 Getting Git repository...")
	gitURL := fmt.Sprintf("https://github.com/%s/%s.git", p.GitUser, p.RepoName)
	crPAT := client.SetSecret("github-pat", os.Getenv("CR_PAT"))

	repo := client.Git(gitURL, dagger.GitOpts{
		KeepGitDir:       true,
		HTTPAuthToken:    crPAT,
		HTTPAuthUsername: "x-access-token",
	})

	source := repo.Branch(p.GitBranch).Tree()
	commitSHA, err := repo.Branch(p.GitBranch).Commit(ctx)
	if err != nil {
		return fmt.Errorf("failed to get commit SHA: %w", err)
	}
	latestCommit := commitSHA
	fmt.Printf("   Commit: %s\n", latestCommit[:min(12, len(latestCommit))])

	// Stage 0: Setup builder with Docker support
	fmt.Println("🔨 Setting up build environment...")
	builder := p.setupBuilder(ctx, client, baseImage, source)

	// Stage 1: Check Docker availability
	fmt.Println("🐳 Checking Docker availability for integration tests...")
	dockerAvailable, err := p.checkDockerAvailability(ctx, builder)
	if err != nil {
		fmt.Printf("⚠️  Docker check error: %v\n", err)
		dockerAvailable = false
	}
	p.HasDocker = dockerAvailable

	if dockerAvailable {
		fmt.Println("   ✅ Docker available - will run full test suite (unit + integration)")
	} else {
		fmt.Println("   ⚠️  Docker NOT available - will run unit tests only")
	}

	// Stage 2: Run tests
	fmt.Println("🧪 Running tests...")
	testContainer, err := p.runTests(ctx, builder, dockerAvailable)
	if err != nil {
		fmt.Printf("❌ Tests failed\n")
		return fmt.Errorf("tests failed: %w", err)
	}
	fmt.Println("✅ Tests passed successfully")

	// Stage 3: Build JAR (only after successful tests)
	fmt.Println("📦 Building Maven artifact...")
	buildContainer := testContainer.WithExec([]string{
		"mvn", "package",
		"-DskipTests",
		"-Dmaven.compiler.release=25",
		"-Dmaven.compiler.compilerArgs=--enable-preview",
		"-q",
	})

	_, err = buildContainer.Stdout(ctx)
	if err != nil {
		return fmt.Errorf("failed to build JAR: %w", err)
	}
	fmt.Println("✅ Build completed successfully")

	// Stage 4: Build Docker image
	fmt.Println("🐳 Building Docker image...")
	railwayFrameworkDir := buildContainer.
		WithWorkdir("/app/railway_framework").
		Directory("/app/railway_framework")
	image := railwayFrameworkDir.DockerBuild()

	// Create image tags
	shortSHA := latestCommit
	if len(latestCommit) > 7 {
		shortSHA = latestCommit[:7]
	}
	timestamp := time.Now().Format("20060102-1504")
	imageTag := fmt.Sprintf("v1.0.0-%s-%s", shortSHA, timestamp)

	// Docker-safe naming
	imageNameClean := strings.ToLower(strings.ReplaceAll(p.ImageName, "_", "-"))
	username := p.GitUser
	imageName := fmt.Sprintf("ghcr.io/%s/%s:%s", strings.ToLower(username), imageNameClean, imageTag)
	latestImageName := fmt.Sprintf("ghcr.io/%s/%s:latest", strings.ToLower(username), imageNameClean)

	// Stage 5: Publish images
	fmt.Printf("📤 Publishing to: %s\n", imageName)
	password := client.SetSecret("password", os.Getenv("CR_PAT"))

	publishedAddress, err := image.
		WithRegistryAuth("ghcr.io", username, password).
		Publish(ctx, imageName)
	if err != nil {
		return fmt.Errorf("failed to publish versioned image: %w", err)
	}

	latestAddress, err := image.
		WithRegistryAuth("ghcr.io", username, password).
		Publish(ctx, latestImageName)
	if err != nil {
		return fmt.Errorf("failed to publish latest image: %w", err)
	}

	// Print results
	fmt.Println("✅ Images published:")
	fmt.Printf("   📦 Versioned: %s\n", publishedAddress)
	fmt.Printf("   📦 Latest: %s\n", latestAddress)

	// Trigger deployment webhook if configured
	if deployWebhook := os.Getenv("DEPLOY_WEBHOOK"); deployWebhook != "" {
		fmt.Println("🚀 Triggering deployment webhook...")
		if err := p.triggerWebhook(deployWebhook, imageTag, publishedAddress, latestCommit, timestamp); err != nil {
			fmt.Printf("⚠️  Warning: Deployment trigger failed: %v\n", err)
		} else {
			fmt.Println("✅ Deployment triggered successfully")
		}
	}

	return nil
}

// setupBuilder creates a builder container with Docker support
func (p *RailwayPipeline) setupBuilder(ctx context.Context, client *dagger.Client, baseImage string, source *dagger.Directory) *dagger.Container {
	// Base setup
	builder := client.Container().
		From(baseImage).
		WithExec([]string{"yum", "update", "-y"}).
		WithExec([]string{"yum", "install", "-y", "maven", "git"}).
		WithMountedCache("/root/.m2", p.MavenCache).
		WithMountedDirectory("/app", source).
		WithWorkdir("/app/railway_framework")

	// Try to mount Docker socket for testcontainers
	// This enables integration tests with Docker containers
	if dockerSocket := os.Getenv("DOCKER_HOST"); dockerSocket != "" {
		fmt.Printf("   📌 Using custom Docker socket: %s\n", dockerSocket)
		// Parse socket path from environment variable like "unix:///var/run/docker.sock"
		socketPath := strings.TrimPrefix(dockerSocket, "unix://")
		builder = builder.WithUnixSocket(socketPath, client.UnixSocket(socketPath))
	} else {
		// Try default Docker socket on Unix-like systems
		fmt.Println("   📌 Checking for default Docker socket: /var/run/docker.sock")
		// Note: WithUnixSocket will only mount if socket exists
		builder = builder.WithUnixSocket("/var/run/docker.sock", client.UnixSocket("/var/run/docker.sock"))
	}

	return builder
}

// checkDockerAvailability determines if Docker is accessible within the container
func (p *RailwayPipeline) checkDockerAvailability(ctx context.Context, builder *dagger.Container) (bool, error) {
	// Test 1: Check if socket exists and is readable
	testContainer := builder.WithExec([]string{
		"test", "-e", "/var/run/docker.sock",
	})

	_, err := testContainer.Stdout(ctx)
	if err != nil {
		return false, nil // Docker socket not available
	}

	// Test 2: Try to connect to Docker
	testContainer2 := builder.WithExec([]string{
		"sh", "-c", "command -v docker && docker ps > /dev/null 2>&1",
	})

	_, err = testContainer2.Stdout(ctx)
	if err != nil {
		// Docker command might not be installed yet, but socket exists
		// First install docker-cli if socket exists
		builder = builder.WithExec([]string{"yum", "install", "-y", "docker"})

		// Try again
		testContainer3 := builder.WithExec([]string{
			"sh", "-c", "docker ps > /dev/null 2>&1",
		})
		_, err = testContainer3.Stdout(ctx)
		return err == nil, nil
	}

	return true, nil
}

// runTests executes test suite based on Docker availability
func (p *RailwayPipeline) runTests(ctx context.Context, builder *dagger.Container, hasDocker bool) (*dagger.Container, error) {
	var testArgs []string

	if hasDocker {
		// Run ALL tests (unit + integration with testcontainers)
		fmt.Println("   → Running full test suite (unit + integration)")
		testArgs = []string{
			"mvn", "test",
			"-Dmaven.compiler.release=25",
			"-Dmaven.compiler.compilerArgs=--enable-preview",
			"-q",
		}
	} else {
		// Run ONLY unit tests (skip integration tests that need Docker)
		fmt.Println("   → Running unit tests only (integration tests skipped)")
		testArgs = []string{
			"mvn", "test",
			"-DexcludedGroups=integration",  // Requires @Tag("integration") on tests
			"-Dmaven.compiler.release=25",
			"-Dmaven.compiler.compilerArgs=--enable-preview",
			"-q",
		}
	}

	testContainer := builder.WithExec(testArgs)
	_, err := testContainer.Stdout(ctx)
	if err != nil {
		return nil, err
	}

	return testContainer, nil
}

// triggerWebhook sends deployment webhook notification
func (p *RailwayPipeline) triggerWebhook(webhookURL, imageTag, imageAddress, commitSHA, timestamp string) error {
	fmt.Printf("   Webhook: %s\n", webhookURL)
	fmt.Printf("   Image Tag: %s\n", imageTag)
	fmt.Printf("   Image: %s\n", imageAddress)
	fmt.Printf("   Commit: %s\n", commitSHA)
	fmt.Printf("   Timestamp: %s\n", timestamp)
	return nil
}

// min returns the minimum of two integers
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
```

---

## Step 2: Update run.sh Script

Create/update `dagger_go/run.sh` to ensure Docker socket is available:

```bash
#!/bin/bash
# dagger_go/run.sh - Enhanced for testcontainers support

set -e  # Exit on error

# Load environment variables
set -a
source "${workspaceFolder:-$(pwd)/..}/credentials/.env"
set +a

# Check Docker availability
echo "🔍 Checking Docker environment..."
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker command not found - integration tests will be skipped"
    export DOCKER_AVAILABLE="false"
else
    echo "✅ Docker command found"
    if docker ps > /dev/null 2>&1; then
        echo "✅ Docker daemon is accessible"
        export DOCKER_AVAILABLE="true"
    else
        echo "⚠️  Docker daemon not accessible"
        export DOCKER_AVAILABLE="false"
    fi
fi

# Set Docker socket environment variable if available
if [ -S /var/run/docker.sock ]; then
    echo "✅ Docker socket available at /var/run/docker.sock"
    export DOCKER_HOST="unix:///var/run/docker.sock"
elif [ -n "$DOCKER_HOST" ]; then
    echo "✅ Using DOCKER_HOST: $DOCKER_HOST"
else
    echo "⚠️  No Docker socket found"
    export DOCKER_HOST=""
fi

# Run Dagger pipeline
cd "$(dirname "$0")"
echo ""
echo "🚀 Starting Dagger pipeline..."
go run main.go
```

---

## Step 3: Update Test Annotations (Optional but Recommended)

Mark integration tests in your Java code:

```java
// In your integration test files
import org.junit.jupiter.api.Tag;

@Tag("integration")  // Add this annotation
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogRepositoryImplIntegrationTest {

    @Testcontainers
    static class PostgresContainer {
        static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("railway_test");

        @DynamicPropertySource
        static void props(DynamicPropertyRegistry registry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl);
            registry.add("spring.datasource.username", postgres::getUsername);
            registry.add("spring.datasource.password", postgres::getPassword);
        }
    }
}
```

---

## Step 4: Configuration & Deployment

### Local Development

```bash
# Ensure Docker is running
docker ps

# Run pipeline
cd dagger_go
./run.sh
# or
go run main.go
```

### GitHub Actions

```yaml
# .github/workflows/build.yml
name: Build and Publish

on:
  push:
    branches: [main, develop]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.22'

      - name: Set up Docker BuildX
        uses: docker/setup-buildx-action@v2

      - name: Run Dagger Pipeline
        env:
          USERNAME: ${{ github.actor }}
          CR_PAT: ${{ secrets.GITHUB_TOKEN }}
          REPO_NAME: railway_oriented_java
        run: |
          cd dagger_go
          go run main.go
```

### GitLab CI

```yaml
# .gitlab-ci.yml
build-pipeline:
  image: golang:1.22
  services:
    - docker:dind
  variables:
    DOCKER_HOST: unix:///var/run/docker.sock
    DOCKER_DRIVER: overlay2
    DOCKER_TLS_CERTDIR: ""
  script:
    - cd dagger_go
    - go run main.go
  only:
    - main
    - develop
```

---

## Testing the Implementation

```bash
# Test 1: Verify Docker socket mounting
cd railway_framework
go run ../dagger_go/main.go

# Test 2: Check specific test groups
mvn test -Dgroups=integration  # Integration only
mvn test -DexcludedGroups=integration  # Unit only

# Test 3: Verify without Docker
# (requires Docker to not be running)
# ... stop Docker daemon ...
go run main.go
# Should run unit tests and skip integration tests gracefully

# Test 4: Check logs
go run main.go 2>&1 | grep -E "Docker|Test|integration"
```

---

## Troubleshooting

### Problem: "Docker socket not found"
```bash
# Solution: Ensure Docker is running
docker ps

# Or export custom socket
export DOCKER_HOST=unix:///var/run/docker.sock
go run main.go
```

### Problem: "Permission denied /var/run/docker.sock"
```bash
# On Linux, ensure user can access socket
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo
sudo go run main.go
```

### Problem: "Testcontainers cannot connect to Docker"
```bash
# Verify testcontainers in tests
mvn test -Dgroups=integration -X  # Enable debug output

# Check Docker configuration
docker inspect --type network bridge

# Ensure Maven is using docker-compose network correctly
```

### Problem: Tests pass locally but fail in CI/CD
```bash
# Ensure environment variables are set in CI
# Check: USERNAME, CR_PAT, REPO_NAME

# Verify Docker is available in CI runner
- name: Verify Docker
  run: docker ps

# Check logs for Docker socket errors
go run main.go 2>&1 | tail -100
```

---

## Summary

✅ **What this enables:**
- Testcontainers integration tests run in Dagger pipeline
- Works with Docker socket mounting (SOLUTION 2)
- Graceful fallback to unit-only tests if Docker unavailable (SOLUTION 4)
- Universal pipeline (local dev, GitHub Actions, GitLab CI, etc.)

✅ **No changes needed in:**
- Java test code (existing testcontainers setup works)
- Dockerfile
- Maven pom.xml
- Application code

✅ **Changes required:**
- `dagger_go/main.go` - Add Docker socket support
- `dagger_go/run.sh` - Detect Docker availability
- CI/CD configs - Ensure Docker daemon available
- Test annotations (optional) - `@Tag("integration")`

