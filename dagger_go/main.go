package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"runtime"
	"strings"
	"time"

	"dagger.io/dagger"
)

// Constants
const (
	baseImage                 = "python:3.14-slim"
	appWorkdir                = "/app"
	containerDockerSocketPath = "/var/run/docker.sock"
	dockerUnixPrefix          = "unix://"
	separatorLine             = "─────────────────────────────────────────────────────────────────────────────────"
)

// Pipeline represents a universal Python CI/CD pipeline.
// All project-specific values (name, image name) are discovered at runtime
// from pyproject.toml inside the cloned repository — nothing is hardcoded.
// Test stages are individually configurable via environment variables.
type Pipeline struct {
	RepoName            string // GitHub repository name (e.g. "cert-parser")
	ProjectName         string // Python project name from pyproject.toml
	ImageName           string // Docker image name (default: RepoName, Docker-safe)
	GitRepo             string // Full clone URL
	GitBranch           string // Branch to build
	GitUser             string // GitHub username
	PipCache            *dagger.CacheVolume
	RunUnitTests        bool // Whether to run unit tests (default: true)
	RunIntegrationTests bool // Whether to run integration tests (default: true)
	RunAcceptanceTests  bool // Whether to run acceptance tests (default: true)
	RunLint             bool // Whether to run ruff lint (default: true)
	RunTypeCheck        bool // Whether to run mypy type check (default: true)
	HasDocker           bool // Docker available on host for testcontainers
}

// main runs the CI/CD pipeline.
// Project name is auto-discovered from pyproject.toml unless overridden.
// Required: CR_PAT, USERNAME.
//
// Test configuration environment variables:
//
//	RUN_UNIT_TESTS=true|false         (default: true)
//	RUN_INTEGRATION_TESTS=true|false  (default: true)  — requires Docker
//	RUN_ACCEPTANCE_TESTS=true|false   (default: true)   — requires Docker
//	RUN_LINT=true|false               (default: true)
//	RUN_TYPE_CHECK=true|false         (default: true)
func main() {
	ctx := context.Background()

	// Check required environment variables
	for _, v := range []string{"CR_PAT", "USERNAME"} {
		if _, ok := os.LookupEnv(v); !ok {
			fmt.Fprintf(os.Stderr, "ERROR: %s environment variable must be set\n", v)
			os.Exit(1)
		}
	}

	username := os.Getenv("USERNAME")
	repoName := envOrDefault("REPO_NAME", "")
	gitBranch := envOrDefault("GIT_BRANCH", "main")
	imageName := envOrDefault("IMAGE_NAME", "")

	// Parse configurable pipeline stages
	runUnitTests := parseEnvBool("RUN_UNIT_TESTS", true)
	runIntegrationTests := parseEnvBool("RUN_INTEGRATION_TESTS", true)
	runAcceptanceTests := parseEnvBool("RUN_ACCEPTANCE_TESTS", true)
	runLint := parseEnvBool("RUN_LINT", true)
	runTypeCheck := parseEnvBool("RUN_TYPE_CHECK", true)

	fmt.Println("🚀 Starting Python CI/CD Pipeline (Go SDK v0.19.7)...")
	fmt.Printf("   GitHub User: %s\n", username)
	fmt.Printf("   Branch: %s\n", gitBranch)
	fmt.Println("🧪 Test Configuration:")
	fmt.Printf("   Unit tests:        %v (RUN_UNIT_TESTS)\n", runUnitTests)
	fmt.Printf("   Integration tests: %v (RUN_INTEGRATION_TESTS)\n", runIntegrationTests)
	fmt.Printf("   Acceptance tests:  %v (RUN_ACCEPTANCE_TESTS)\n", runAcceptanceTests)
	fmt.Printf("   Lint (ruff):       %v (RUN_LINT)\n", runLint)
	fmt.Printf("   Type check (mypy): %v (RUN_TYPE_CHECK)\n", runTypeCheck)

	if !runUnitTests && !runIntegrationTests && !runAcceptanceTests {
		fmt.Println("⚠️  All test stages disabled — skipping tests, proceeding to lint/build/push")
	}

	// Initialize Dagger client
	client, err := dagger.Connect(ctx, dagger.WithLogOutput(os.Stderr))
	if err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Failed to create Dagger client: %v\n", err)
		os.Exit(1)
	}
	defer client.Close()

	pipeline := &Pipeline{
		RepoName:            repoName,
		ImageName:           imageName,
		GitBranch:           gitBranch,
		GitUser:             username,
		RunUnitTests:        runUnitTests,
		RunIntegrationTests: runIntegrationTests,
		RunAcceptanceTests:  runAcceptanceTests,
		RunLint:             runLint,
		RunTypeCheck:        runTypeCheck,
	}

	if err := pipeline.run(ctx, client); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Pipeline failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("\n🎉 Pipeline completed successfully!")
}

// run executes the full pipeline:
// Clone → Discover → Install → Unit Tests → Integration Tests → Acceptance Tests
// → Lint → Type-check → Docker Build → Publish
func (p *Pipeline) run(ctx context.Context, client *dagger.Client) error {
	// ── Clone repository from GitHub ─────────────────────────────
	crPAT := client.SetSecret("github-pat", os.Getenv("CR_PAT"))

	if p.RepoName == "" {
		return fmt.Errorf("REPO_NAME environment variable is required (e.g. 'cert-parser')")
	}

	gitURL := fmt.Sprintf("https://github.com/%s/%s.git", p.GitUser, p.RepoName)
	p.GitRepo = gitURL
	fmt.Printf("\n📥 Cloning repository: %s (branch: %s)\n", gitURL, p.GitBranch)

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
	fmt.Printf("   Commit: %s\n", commitSHA[:min(12, len(commitSHA))])

	// ── Discover project name from pyproject.toml ────────────────
	fmt.Println("🔍 Discovering project name from pyproject.toml...")

	pyprojectContent, err := source.File("pyproject.toml").Contents(ctx)
	if err != nil {
		return fmt.Errorf("failed to read pyproject.toml: %w", err)
	}

	projectName := extractProjectName(pyprojectContent)
	if projectName == "" {
		projectName = p.RepoName
		fmt.Printf("   ⚠️  Could not parse name from pyproject.toml, using repo name: %s\n", projectName)
	} else {
		fmt.Printf("   Project name: %s\n", projectName)
	}
	p.ProjectName = projectName

	if p.ImageName == "" {
		p.ImageName = dockerSafeName(projectName)
	}

	// ── Check Docker availability for testcontainers ─────────────
	needsDocker := p.RunIntegrationTests || p.RunAcceptanceTests
	if needsDocker {
		fmt.Println("🔍 Checking Docker availability for testcontainers...")
		hostDockerPath := getDockerSocketPath()
		if hostDockerPath != "" {
			p.HasDocker = true
			fmt.Printf("   ✅ Docker socket detected: %s\n", hostDockerPath)
		} else {
			p.HasDocker = false
			fmt.Printf("   ⚠️  Docker socket NOT available (OS: %s)\n", runtime.GOOS)
			if p.RunIntegrationTests {
				fmt.Println("   Integration tests will be SKIPPED (require Docker)")
			}
			if p.RunAcceptanceTests {
				fmt.Println("   Acceptance tests will be SKIPPED (require Docker)")
			}
		}
	}

	// ── Set up build environment (Dagger container) ──────────────
	fmt.Println("🔨 Setting up Python build environment...")

	p.PipCache = client.CacheVolume("pip-cache-" + dockerSafeName(p.RepoName))

	builder := client.Container().
		From(baseImage).
		WithExec([]string{"apt-get", "update"}).
		WithExec([]string{"apt-get", "install", "-y", "--no-install-recommends",
			"git", "build-essential", "libpq-dev"}).
		WithExec([]string{"rm", "-rf", "/var/lib/apt/lists/*"}).
		WithMountedCache("/root/.cache/pip", p.PipCache).
		WithMountedDirectory(appWorkdir, source).
		WithWorkdir(appWorkdir).
		WithExec([]string{"pip", "install", "--upgrade", "pip", "setuptools", "wheel"})

	// Install the local framework dependency first, then the project with dev+server extras
	builder = builder.
		WithExec([]string{"pip", "install", "-e", "./python_framework"}).
		WithExec([]string{"pip", "install", "-e", ".[dev,server]"})

	stageNum := 0

	// ── Stage: Unit Tests (inside Dagger container) ──────────────
	if p.RunUnitTests {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: UNIT TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Dagger container (isolated, no Docker needed)")
		fmt.Println("🧪 Running: pytest -m \"not integration and not acceptance\"")
		fmt.Println(separatorLine)

		testContainer := builder.WithExec([]string{
			"pytest", "-v", "--tb=short",
			"-m", "not integration and not acceptance",
		})

		testOutput, err := testContainer.Stdout(ctx)
		if err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: UNIT TESTS\n", stageNum)
			return fmt.Errorf("unit tests failed: %w", err)
		}
		fmt.Println(testOutput)
		fmt.Printf("✅ STAGE %d COMPLETE: All unit tests passed\n", stageNum)

		builder = testContainer
	}

	// ── Stage: Integration Tests (on host — testcontainers needs Docker) ──
	if p.RunIntegrationTests && p.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: INTEGRATION TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Host machine (testcontainers requires native Docker)")
		fmt.Println("🐘 PostgreSQL: Testcontainers will start a real PostgreSQL instance")
		fmt.Println("🧪 Running: pytest -v --tb=short -m integration")
		fmt.Println(separatorLine)

		if err := p.runTestsOnHost(ctx, "integration"); err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: INTEGRATION TESTS\n", stageNum)
			return fmt.Errorf("integration tests failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: All integration tests passed\n", stageNum)
	} else if p.RunIntegrationTests && !p.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: INTEGRATION TESTS — SKIPPED\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("   ⏭️  Docker not available — testcontainers cannot start PostgreSQL")
	}

	// ── Stage: Acceptance Tests (on host — testcontainers needs Docker) ──
	if p.RunAcceptanceTests && p.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: ACCEPTANCE TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Host machine (testcontainers requires native Docker)")
		fmt.Println("🐘 PostgreSQL: Testcontainers will start a real PostgreSQL instance")
		fmt.Println("📦 Fixtures: Real ICAO .bin/.der fixtures used for end-to-end verification")
		fmt.Println("🧪 Running: pytest -v --tb=short -m acceptance")
		fmt.Println(separatorLine)

		if err := p.runTestsOnHost(ctx, "acceptance"); err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: ACCEPTANCE TESTS\n", stageNum)
			return fmt.Errorf("acceptance tests failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: All acceptance tests passed\n", stageNum)
	} else if p.RunAcceptanceTests && !p.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: ACCEPTANCE TESTS — SKIPPED\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("   ⏭️  Docker not available — testcontainers cannot start PostgreSQL")
	}

	// ── Stage: Lint ──────────────────────────────────────────────
	if p.RunLint {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: LINT (ruff)\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("🔍 Running ruff check src/ tests/...")

		lintContainer := builder.WithExec([]string{
			"ruff", "check", "src/", "tests/",
		})

		_, err = lintContainer.Stdout(ctx)
		if err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: LINT\n", stageNum)
			return fmt.Errorf("ruff lint failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: Lint passed\n", stageNum)
		builder = lintContainer
	}

	// ── Stage: Type Check ────────────────────────────────────────
	if p.RunTypeCheck {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: TYPE CHECK (mypy)\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("🔍 Running mypy src/ --strict...")

		typeContainer := builder.WithExec([]string{
			"mypy", "src/", "--strict",
		})

		_, err = typeContainer.Stdout(ctx)
		if err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: TYPE CHECK\n", stageNum)
			return fmt.Errorf("mypy type check failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: Type check passed\n", stageNum)
	}

	// ── Stage: Docker Build ──────────────────────────────────────
	stageNum++
	fmt.Printf("\n%s\n", strings.Repeat("=", 80))
	fmt.Printf("PIPELINE STAGE %d: BUILD DOCKER IMAGE\n", stageNum)
	fmt.Println(strings.Repeat("=", 80))
	fmt.Println("🐳 Building Docker image from Dockerfile...")

	image := source.DockerBuild()

	shortSHA := commitSHA
	if len(commitSHA) > 7 {
		shortSHA = commitSHA[:7]
	}
	timestamp := time.Now().Format("20060102-1504")
	imageTag := fmt.Sprintf("v0.1.0-%s-%s", shortSHA, timestamp)

	imageNameClean := dockerSafeName(p.ImageName)
	userLower := strings.ToLower(p.GitUser)
	versionedImage := fmt.Sprintf("ghcr.io/%s/%s:%s", userLower, imageNameClean, imageTag)
	latestImage := fmt.Sprintf("ghcr.io/%s/%s:latest", userLower, imageNameClean)

	fmt.Printf("   Image: %s\n", versionedImage)
	fmt.Printf("✅ STAGE %d COMPLETE: Docker image built\n", stageNum)

	// ── Stage: Publish to GHCR ───────────────────────────────────
	stageNum++
	fmt.Printf("\n%s\n", strings.Repeat("=", 80))
	fmt.Printf("PIPELINE STAGE %d: PUBLISH TO GHCR\n", stageNum)
	fmt.Println(strings.Repeat("=", 80))
	fmt.Printf("📤 Publishing to: %s\n", versionedImage)

	password := client.SetSecret("password", os.Getenv("CR_PAT"))

	publishedAddress, err := image.
		WithRegistryAuth("ghcr.io", p.GitUser, password).
		Publish(ctx, versionedImage)
	if err != nil {
		return fmt.Errorf("failed to publish versioned image: %w", err)
	}

	latestAddress, err := image.
		WithRegistryAuth("ghcr.io", p.GitUser, password).
		Publish(ctx, latestImage)
	if err != nil {
		return fmt.Errorf("failed to publish latest image: %w", err)
	}

	fmt.Printf("✅ STAGE %d COMPLETE: Images published\n", stageNum)
	fmt.Printf("   📦 Versioned: %s\n", publishedAddress)
	fmt.Printf("   📦 Latest:    %s\n", latestAddress)

	return nil
}

// ── Host-based test execution ────────────────────────────────────

// runTestsOnHost executes pytest with a specific marker on the HOST machine
// (not inside the Dagger container). This is necessary for integration and
// acceptance tests that use testcontainers, because testcontainers requires
// native Docker socket access — Docker-in-Docker path mismatches inside Dagger
// containers prevent testcontainers from binding volumes correctly.
//
// Requires: the project's virtualenv to be installed on the host machine.
// The function auto-discovers the project root (parent of dagger_go/) and
// runs pytest from there using the local .venv.
func (p *Pipeline) runTestsOnHost(ctx context.Context, marker string) error {
	cwd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("failed to get current directory: %w", err)
	}

	// When running from dagger_go/, the project root is ../
	projectRoot := cwd + "/.."

	fmt.Println("⚙️  Configuration:")
	fmt.Printf("   • Project root: %s\n", projectRoot)
	fmt.Printf("   • Marker: %s\n", marker)
	fmt.Printf("   • Command: pytest -v --tb=short -m %s\n", marker)
	fmt.Println("")

	// Determine pytest executable — prefer .venv/bin/pytest, fall back to PATH
	pytestBin := projectRoot + "/.venv/bin/pytest"
	if _, err := os.Stat(pytestBin); err != nil {
		// Try system pytest
		pytestBin = "pytest"
		fmt.Println("   ⚠️  .venv not found, using system pytest")
	} else {
		fmt.Printf("   • Using: %s\n", pytestBin)
	}

	cmd := exec.CommandContext(ctx, pytestBin, "-v", "--tb=short", "-m", marker)
	cmd.Dir = projectRoot

	// Capture output while streaming to stdout
	var outputBuffer strings.Builder
	multiWriter := io.MultiWriter(os.Stdout, &outputBuffer)
	cmd.Stdout = multiWriter
	cmd.Stderr = os.Stderr

	start := time.Now()
	err = cmd.Run()
	duration := time.Since(start)

	fmt.Println(separatorLine)
	displayHostTestSummary(marker, outputBuffer.String(), duration, err)

	if err != nil {
		return fmt.Errorf("%s tests failed: %w", marker, err)
	}
	return nil
}

// displayHostTestSummary parses pytest output and shows a summary
func displayHostTestSummary(marker string, output string, duration time.Duration, testErr error) {
	// Parse pytest summary line: "X passed, Y failed, Z errors in Ns"
	summaryPattern := regexp.MustCompile(`(\d+) passed`)
	failedPattern := regexp.MustCompile(`(\d+) failed`)
	errorPattern := regexp.MustCompile(`(\d+) error`)

	lines := strings.Split(output, "\n")
	var summaryLine string
	for _, line := range lines {
		if strings.Contains(line, "passed") || strings.Contains(line, "failed") {
			if strings.Contains(line, "====") {
				summaryLine = line
			}
		}
	}

	fmt.Printf("\n📊 %s Test Summary\n", strings.ToUpper(marker[:1])+marker[1:])
	fmt.Println(separatorLine)

	if summaryLine != "" {
		passed := "0"
		failed := "0"
		errors := "0"
		if m := summaryPattern.FindStringSubmatch(summaryLine); m != nil {
			passed = m[1]
		}
		if m := failedPattern.FindStringSubmatch(summaryLine); m != nil {
			failed = m[1]
		}
		if m := errorPattern.FindStringSubmatch(summaryLine); m != nil {
			errors = m[1]
		}
		fmt.Printf("   Passed: %s | Failed: %s | Errors: %s | Duration: %v\n",
			passed, failed, errors, duration.Round(time.Millisecond))
	} else {
		fmt.Printf("   Duration: %v\n", duration.Round(time.Millisecond))
	}

	if testErr != nil {
		fmt.Printf("   ❌ FAILED: %s tests failed after %v\n", marker, duration.Round(time.Millisecond))
	} else {
		fmt.Printf("   ✅ SUCCESS: %s tests passed in %v\n", marker, duration.Round(time.Millisecond))
	}
	fmt.Println("")
}

// ── Docker socket detection ─────────────────────────────────────

// getDockerSocketPath returns the Docker socket path for the current platform.
// Returns empty string if Docker is not available.
func getDockerSocketPath() string {
	var candidates []string

	switch runtime.GOOS {
	case "windows":
		candidates = []string{
			`\\.\pipe\docker_engine`,
			`//./pipe/docker_engine`,
		}
	case "darwin":
		candidates = []string{
			"/var/run/docker.sock",
			os.Getenv("HOME") + "/.docker/run/docker.sock",
			os.Getenv("HOME") + "/.colima/docker.sock",
		}
	default:
		candidates = []string{
			"/var/run/docker.sock",
			"/run/docker.sock",
			os.Getenv("DOCKER_HOST"),
		}
	}

	for _, path := range candidates {
		if path == "" {
			continue
		}
		path = strings.TrimPrefix(path, dockerUnixPrefix)
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}
	return ""
}

// ── Helpers ──────────────────────────────────────────────────────

// extractProjectName parses the `name = "..."` field from pyproject.toml content.
func extractProjectName(content string) string {
	re := regexp.MustCompile(`(?m)^name\s*=\s*"([^"]+)"`)
	matches := re.FindStringSubmatch(content)
	if len(matches) >= 2 {
		return matches[1]
	}
	return ""
}

// dockerSafeName converts a project name to a Docker-safe image name.
func dockerSafeName(name string) string {
	return strings.ToLower(strings.ReplaceAll(name, "_", "-"))
}

// envOrDefault returns the value of an environment variable, or a default.
func envOrDefault(key, defaultValue string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultValue
}

// parseEnvBool parses boolean environment variables with default value.
// Accepts: true, True, TRUE, 1, yes, Yes, YES.
func parseEnvBool(envVar string, defaultValue bool) bool {
	value := os.Getenv(envVar)
	if value == "" {
		return defaultValue
	}
	lowerValue := strings.ToLower(value)
	return lowerValue == "true" || lowerValue == "1" || lowerValue == "yes"
}

// min returns the minimum of two integers.
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
