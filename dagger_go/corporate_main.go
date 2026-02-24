//go:build corporate

package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"dagger.io/dagger"
)

// Constants for corporate pipeline
const (
	corporateSeparatorLine = "─────────────────────────────────────────────────────────────────────────────────"
	baseImageCorporate     = "python:3.14-slim"
	appWorkdirCorporate    = "/app"
	dockerUnixPrefixCorp   = "unix://"
)

// CorporatePipeline represents the cert-parser CI/CD pipeline with corporate
// MITM proxy and custom CA certificate support. All project-specific values
// (name, image name) are discovered at runtime from pyproject.toml — nothing
// is hardcoded. Test stages are individually configurable via environment variables.
type CorporatePipeline struct {
	RepoName            string
	ProjectName         string // Discovered from pyproject.toml
	ImageName           string
	GitRepo             string
	GitBranch           string
	GitUser             string
	PipCache            *dagger.CacheVolume // pip package cache
	HasDocker           bool                // Docker available on host for testcontainers
	RunUnitTests        bool                // Run pytest unit tests (default: true)
	RunIntegrationTests bool                // Run pytest integration tests (default: true)
	RunAcceptanceTests  bool                // Run pytest acceptance tests (default: true)
	RunLint             bool                // Run ruff lint (default: true)
	RunTypeCheck        bool                // Run mypy type check (default: true)
	CACertPaths         []string            // Paths to CA certificates
	ProxyURL            string              // HTTP proxy URL
	DebugMode           bool                // Enable certificate discovery diagnostics
}

// parseEnvBool parses boolean environment variables with a default fallback
func parseEnvBool(key string, defaultValue bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	value = strings.ToLower(value)
	return value == "true" || value == "1" || value == "yes"
}

// main runs the cert-parser CI/CD pipeline with corporate MITM proxy and
// custom CA certificate support. Mirrors main.go but adds CA/proxy handling.
//
// Required: CR_PAT, USERNAME, REPO_NAME.
//
// Optional:
//
//	GIT_BRANCH=main            (default: main)
//	IMAGE_NAME=<name>          (default: auto-discovered from pyproject.toml)
//	HTTP_PROXY / HTTPS_PROXY   MITM proxy URL
//	DEBUG_CERTS=true           Enable certificate discovery diagnostics
//	CA_CERTIFICATES_PATH=...   Colon-separated paths to CA certs
//
// Test configuration environment variables (all default true):
//
//	RUN_UNIT_TESTS=true|false
//	RUN_INTEGRATION_TESTS=true|false   — requires Docker on host
//	RUN_ACCEPTANCE_TESTS=true|false    — requires Docker on host
//	RUN_LINT=true|false
//	RUN_TYPE_CHECK=true|false
func main() {
	ctx := context.Background()

	// Require CR_PAT and USERNAME
	for _, v := range []string{"CR_PAT", "USERNAME"} {
		if _, ok := os.LookupEnv(v); !ok {
			fmt.Fprintf(os.Stderr, "ERROR: %s environment variable must be set\n", v)
			os.Exit(1)
		}
	}

	if repoName := os.Getenv("REPO_NAME"); repoName == "" {
		fmt.Fprintf(os.Stderr, "ERROR: REPO_NAME environment variable must be set (e.g. 'cert-parser')\n")
		os.Exit(1)
	}

	debugMode := os.Getenv("DEBUG_CERTS") == "true"
	proxyURL := os.Getenv("HTTP_PROXY")
	if proxyURL == "" {
		proxyURL = os.Getenv("HTTPS_PROXY")
	}

	username := os.Getenv("USERNAME")
	repoName := os.Getenv("REPO_NAME")
	gitBranch := envOrDefaultCorp("GIT_BRANCH", "main")
	imageName := os.Getenv("IMAGE_NAME") // empty is fine — auto-discovered later

	runUnitTests := parseEnvBool("RUN_UNIT_TESTS", true)
	runIntegrationTests := parseEnvBool("RUN_INTEGRATION_TESTS", true)
	runAcceptanceTests := parseEnvBool("RUN_ACCEPTANCE_TESTS", true)
	runLint := parseEnvBool("RUN_LINT", true)
	runTypeCheck := parseEnvBool("RUN_TYPE_CHECK", true)

	if !runUnitTests && !runIntegrationTests && !runAcceptanceTests {
		fmt.Fprintf(os.Stderr, "ERROR: At least one test stage must be enabled\n")
		os.Exit(1)
	}

	fmt.Println("🏢 CORPORATE MODE: MITM Proxy & Custom CA Support")
	if debugMode {
		fmt.Println("   🔍 Debug mode: ENABLED — certificate discovery diagnostics active")
	}
	if proxyURL != "" {
		fmt.Printf("   🌐 Proxy: %s\n", proxyURL)
	}
	fmt.Printf("🚀 Starting Python CI/CD Pipeline (Go SDK v0.19.7 - Corporate Mode)...\n")
	fmt.Printf("   GitHub User : %s\n", username)
	fmt.Printf("   Repository  : %s (branch: %s)\n", repoName, gitBranch)
	fmt.Println("🧪 Test Configuration:")
	fmt.Printf("   Unit tests:        %v (RUN_UNIT_TESTS)\n", runUnitTests)
	fmt.Printf("   Integration tests: %v (RUN_INTEGRATION_TESTS)\n", runIntegrationTests)
	fmt.Printf("   Acceptance tests:  %v (RUN_ACCEPTANCE_TESTS)\n", runAcceptanceTests)
	fmt.Printf("   Lint (ruff):       %v (RUN_LINT)\n", runLint)
	fmt.Printf("   Type check (mypy): %v (RUN_TYPE_CHECK)\n", runTypeCheck)

	// Initialize Dagger client
	client, err := dagger.Connect(ctx, dagger.WithLogOutput(os.Stderr))
	if err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Failed to create Dagger client: %v\n", err)
		os.Exit(1)
	}
	defer client.Close()

	// Collect CA certificates from credentials/certs/ and system stores
	caCertPaths := collectCACertificates()
	if len(caCertPaths) > 0 {
		fmt.Printf("   📜 Found %d CA certificate path(s)\n", len(caCertPaths))
		validCerts := 0
		for _, cert := range caCertPaths {
			fmt.Printf("      - %s", filepath.Base(cert))
			if err := validateCertificatePath(cert); err != nil {
				fmt.Printf(" ❌ INVALID: %v\n", err)
				continue
			}
			fmt.Println(" ✅")
			validCerts++
		}
		if validCerts == 0 {
			fmt.Println("\n   ⚠️  WARNING: No valid certificates found after validation")
		}
	} else {
		fmt.Println("   ℹ️  No CA certificates discovered automatically")
		fmt.Println("      Tip: Place .pem files in credentials/certs/ for corporate MITM support")
		fmt.Println("      Or set CA_CERTIFICATES_PATH environment variable")
	}

	pipeline := &CorporatePipeline{
		RepoName:            repoName,
		ImageName:           imageName,
		GitBranch:           gitBranch,
		GitUser:             username,
		RunUnitTests:        runUnitTests,
		RunIntegrationTests: runIntegrationTests,
		RunAcceptanceTests:  runAcceptanceTests,
		RunLint:             runLint,
		RunTypeCheck:        runTypeCheck,
		CACertPaths:         caCertPaths,
		ProxyURL:            proxyURL,
		DebugMode:           debugMode,
	}

	if debugMode {
		if err := pipeline.runDiagnostics(ctx, client); err != nil {
			fmt.Printf("⚠️  Diagnostic mode had warnings (continuing anyway): %v\n", err)
		}
	}

	if err := pipeline.runCorporate(ctx, client); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: Pipeline failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("\n🎉 Corporate pipeline completed successfully!")
}

// collectCACertificates auto-discovers certificates from multiple sources
func collectCACertificates() []string {
	var certPaths []string
	discoveredCerts := make(map[string]bool) // Track unique certificates

	// Certificate discovery statistics
	stats := struct {
		attempts  int
		successes int
		notFound  int
		errors    int
	}{}

	debugMode := os.Getenv("DEBUG_CERTS") == "true"

	if debugMode {
		fmt.Println("\n📜 Certificate Discovery - Detailed Log")
		fmt.Println(corporateSeparatorLine)
	}

	// 1. First: Try to collect from credentials/certs/ (user-provided)
	certsDir := "credentials/certs"
	if debugMode {
		fmt.Println("\n🔍 Source: User-provided certificates (credentials/certs/)")
	}
	stats.attempts++
	if _, err := os.Stat(certsDir); err == nil {
		files, err := os.ReadDir(certsDir)
		if err == nil {
			foundInDir := 0
			for _, file := range files {
				if !file.IsDir() && strings.HasSuffix(file.Name(), ".pem") {
					fullPath := filepath.Join(certsDir, file.Name())
					if _, exists := discoveredCerts[fullPath]; !exists {
						certPaths = append(certPaths, fullPath)
						discoveredCerts[fullPath] = true
						stats.successes++
						foundInDir++
						if debugMode {
							fmt.Printf("   ✅ Found: %s\n", fullPath)
						}
					}
				}
			}
			if debugMode && foundInDir == 0 {
				fmt.Println("   ⚠️  Directory exists but no .pem files found")
				stats.notFound++
			}
		} else {
			if debugMode {
				fmt.Printf("   ❌ Error reading directory: %v\n", err)
			}
			stats.errors++
		}
	} else {
		if debugMode {
			fmt.Println("   ℹ️  Directory not found (this is optional)")
		}
		stats.notFound++
	}

	// 2. Auto-discover from system certificate stores
	username := os.Getenv("USERNAME")
	if debugMode {
		fmt.Println("\n🔍 Source: System certificate stores (50+ locations)")
	}
	systemCertPaths := []string{
		// Linux/Debian
		"/etc/ssl/certs/ca-bundle.crt",
		"/etc/ssl/certs/ca-certificates.crt",
		// Linux/RHEL
		"/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
		// macOS
		"/etc/ssl/cert.pem",
		"/usr/local/etc/openssl/cert.pem",
		// macOS Docker Desktop / Rancher Desktop
		filepath.Join(os.Getenv("HOME"), ".docker/certs.d/docker.io/ca.pem"),
		filepath.Join(os.Getenv("HOME"), ".docker/certs.d/ghcr.io/ca.pem"),
		filepath.Join(os.Getenv("HOME"), ".docker/certs.d"),
		filepath.Join(os.Getenv("HOME"), ".rancher/certs.d"),
		// macOS Docker Desktop Group Containers (sandboxed storage)
		filepath.Join(os.Getenv("HOME"), "Library/Group Containers/group.com.docker/certs"),
		filepath.Join(os.Getenv("HOME"), "Library/Group Containers/group.com.docker/settings/ca-certificates"),
		// Windows via WSL
		"/mnt/c/ProgramData/Microsoft/Windows/Certificates/ca-certificates.pem",
		// Windows native paths
		`C:\ProgramData\Microsoft\Windows\Certificates\ca-certificates.pem`,
		`C:\Users\` + username + `\AppData\Local\Corporate_Certificates\ca-bundle.pem`,
		// Docker Desktop on Windows
		`C:\Users\` + username + `\.docker\certs.d\docker.io\ca.pem`,
		`C:\Users\` + username + `\.docker\certs.d\ghcr.io\ca.pem`,
		`C:\Users\` + username + `\.docker\certs.d`,
		// Rancher Desktop on Windows
		`C:\Users\` + username + `\.rancher\certs.d`,
		`C:\Users\` + username + `\AppData\Local\Rancher Desktop\certs`,
		`C:\Users\` + username + `\AppData\Local\Rancher Desktop\config\certs`,
		// Linux Docker / Rancher Desktop socket
		"/etc/docker/certs.d",
		"/var/lib/docker/certs.d",
		"/etc/rancher/k3s/certs.d",
	}

	systemFound := 0
	for _, systemPath := range systemCertPaths {
		stats.attempts++
		if _, err := os.Stat(systemPath); err == nil {
			if _, exists := discoveredCerts[systemPath]; !exists {
				certPaths = append(certPaths, systemPath)
				discoveredCerts[systemPath] = true
				stats.successes++
				systemFound++
				if debugMode {
					fmt.Printf("   ✅ Found: %s\n", systemPath)
				}
			}
		} else {
			stats.notFound++
		}
	}
	if debugMode && systemFound == 0 {
		fmt.Println("   ⚠️  No system certificates found (checked all standard locations)")
	}

	// 2b. Recursively scan Docker and Rancher Desktop certificate directories (registry-specific)
	if debugMode {
		fmt.Println("\n🔍 Source: Docker/Rancher Desktop directories (recursive scan)")
	}
	rancherCertDirs := []string{
		// Docker Desktop
		filepath.Join(os.Getenv("HOME"), ".docker/certs.d"),
		"/etc/docker/certs.d",
		"/var/lib/docker/certs.d",
		`C:\Users\` + username + `\.docker\certs.d`,
		// Rancher Desktop
		filepath.Join(os.Getenv("HOME"), ".rancher/certs.d"),
		`C:\Users\` + username + `\.rancher\certs.d`,
		`C:\Users\` + username + `\AppData\Local\Rancher Desktop\certs`,
		`C:\Users\` + username + `\AppData\Local\Rancher Desktop\config\certs`,
		"/etc/rancher/k3s/certs.d",
	}
	dockerFound := 0
	for _, certDir := range rancherCertDirs {
		stats.attempts++
		beforeCount := len(certPaths)
		scanDockerCerts(certDir, discoveredCerts, &certPaths, &stats, debugMode)
		afterCount := len(certPaths)
		if afterCount > beforeCount {
			stats.successes++
			dockerFound += (afterCount - beforeCount)
		} else if !fileExists(certDir) {
			stats.notFound++
		}
	}
	if debugMode && dockerFound == 0 {
		fmt.Println("   ℹ️  No Docker/Rancher certificates found (directories may not exist or be empty)")
	}

	// 2c. Extract host system certificates that Docker uses
	// Docker inherits these from the host and makes them available to containers
	if debugMode {
		fmt.Println("\n🔍 Source: Docker host system certificates")
	}
	stats.attempts++
	hostCerts := extractDockerHostCertificates(debugMode, &stats)
	hostFound := 0
	for _, hostCert := range hostCerts {
		if !discoveredCerts[hostCert] {
			certPaths = append(certPaths, hostCert)
			discoveredCerts[hostCert] = true
			stats.successes++
			hostFound++
			if debugMode {
				fmt.Printf("   ✅ Found: %s\n", hostCert)
			}
		}
	}
	if debugMode && hostFound == 0 {
		fmt.Println("   ℹ️  No host certificates found (platform may not use standard locations)")
		stats.notFound++
	}

	// 3. Try to capture from current environment (environment variable)
	if debugMode {
		fmt.Println("\n🔍 Source: CA_CERTIFICATES_PATH environment variable")
	}
	stats.attempts++
	if envCerts := os.Getenv("CA_CERTIFICATES_PATH"); envCerts != "" {
		if debugMode {
			fmt.Printf("   🔍 Checking paths: %s\n", envCerts)
		}
		paths := strings.Split(envCerts, ":")
		envFound := 0
		for _, path := range paths {
			path = strings.TrimSpace(path)
			if path != "" && !discoveredCerts[path] {
				if _, err := os.Stat(path); err == nil {
					certPaths = append(certPaths, path)
					discoveredCerts[path] = true
					stats.successes++
					envFound++
					if debugMode {
						fmt.Printf("   ✅ Found: %s\n", path)
					}
				} else {
					if debugMode {
						fmt.Printf("   ❌ Not found: %s\n", path)
					}
					stats.notFound++
				}
			}
		}
		if debugMode && envFound == 0 {
			fmt.Println("   ⚠️  Environment variable set but no valid certificates found")
		}
	} else {
		if debugMode {
			fmt.Println("   ℹ️  Environment variable not set")
		}
		stats.notFound++
	}

	// 4. Detect Jenkins CI/CD environment certificates
	if debugMode {
		fmt.Println("\n🔍 Source: Jenkins CI/CD environment")
	}
	stats.attempts++
	if jenkinsHome := os.Getenv("JENKINS_HOME"); jenkinsHome != "" {
		if debugMode {
			fmt.Printf("   🏢 Jenkins detected: %s\n", jenkinsHome)
		}
		jenkinsCertPaths := []string{
			filepath.Join(jenkinsHome, "war/WEB-INF/ca-bundle.crt"),
			filepath.Join(jenkinsHome, "certs"),
			filepath.Join(jenkinsHome, "ca-certificates"),
		}
		jenkinsFound := 0
		for _, path := range jenkinsCertPaths {
			if _, err := os.Stat(path); err == nil {
				if !discoveredCerts[path] {
					certPaths = append(certPaths, path)
					discoveredCerts[path] = true
					stats.successes++
					jenkinsFound++
					if debugMode {
						fmt.Printf("   ✅ Found: %s\n", path)
					}
				}
			} else {
				stats.notFound++
			}
		}
		if debugMode && jenkinsFound == 0 {
			fmt.Println("   ⚠️  Jenkins detected but no certificates found in standard locations")
		}
	} else {
		if debugMode {
			fmt.Println("   ℹ️  Not running in Jenkins (JENKINS_HOME not set)")
		}
		stats.notFound++
	}

	// 5. Detect GitHub Actions runner environment
	if debugMode {
		fmt.Println("\n🔍 Source: GitHub Actions runner environment")
	}
	stats.attempts++
	if runnerTemp := os.Getenv("RUNNER_TEMP"); runnerTemp != "" {
		if debugMode {
			fmt.Printf("   🐙 GitHub Actions detected: %s\n", runnerTemp)
		}
		customCertsPath := filepath.Join(runnerTemp, "ca-certificates")
		if _, err := os.Stat(customCertsPath); err == nil {
			if !discoveredCerts[customCertsPath] {
				certPaths = append(certPaths, customCertsPath)
				discoveredCerts[customCertsPath] = true
				stats.successes++
				if debugMode {
					fmt.Printf("   ✅ Found: %s\n", customCertsPath)
				}
			}
		} else {
			if debugMode {
				fmt.Println("   ⚠️  GitHub Actions detected but no custom certificates found")
			}
			stats.notFound++
		}
	} else {
		if debugMode {
			fmt.Println("   ℹ️  Not running in GitHub Actions (RUNNER_TEMP not set)")
		}
		stats.notFound++
	}

	// Summary statistics
	if debugMode {
		fmt.Println("\n📊 Certificate Discovery Summary")
		fmt.Println(corporateSeparatorLine)
		fmt.Printf("   🔍 Total sources checked: %d\n", stats.attempts)
		fmt.Printf("   ✅ Certificates found: %d\n", stats.successes)
		fmt.Printf("   ℹ️  Not found: %d\n", stats.notFound)
		if stats.errors > 0 {
			fmt.Printf("   ❌ Errors: %d\n", stats.errors)
		}
		fmt.Printf("   📜 Unique certificates collected: %d\n", len(certPaths))
		fmt.Println(corporateSeparatorLine)
	}

	return certPaths
}

// fileExists checks if a file exists
func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// scanDockerCerts recursively scans Docker certificate directories for .pem and .crt files
func scanDockerCerts(dockerDir string, discovered map[string]bool, paths *[]string, stats *struct {
	attempts  int
	successes int
	notFound  int
	errors    int
}, debugMode bool) {
	if !fileExists(dockerDir) {
		if debugMode {
			fmt.Printf("   ℹ️  Directory not found: %s\n", dockerDir)
		}
		return
	}
	if debugMode {
		fmt.Printf("   🔍 Scanning: %s\n", dockerDir)
	}
	filesFound := 0
	filepath.Walk(dockerDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			if debugMode {
				fmt.Printf("   ⚠️  Error walking path %s: %v\n", path, err)
			}
			stats.errors++
			return nil
		}
		if info.IsDir() {
			return nil
		}
		if strings.HasSuffix(info.Name(), ".pem") || strings.HasSuffix(info.Name(), ".crt") {
			if !discovered[path] {
				*paths = append(*paths, path)
				discovered[path] = true
				filesFound++
				if debugMode {
					fmt.Printf("      ✅ %s\n", path)
				}
			}
		}
		return nil
	})
	if debugMode && filesFound > 0 {
		fmt.Printf("   📊 Found %d certificate(s) in this directory\n", filesFound)
	}
}

// extractDockerHostCertificates extracts certificates from the Docker/Rancher daemon's CA store
// This captures the host system certificates that Docker/Rancher inherited and makes available
func extractDockerHostCertificates(debugMode bool, stats *struct {
	attempts  int
	successes int
	notFound  int
	errors    int
}) []string {
	var hostCerts []string
	username := os.Getenv("USERNAME")

	// On Windows: Docker Desktop and Rancher Desktop use Windows Certificate Store
	windowsCertPaths := []string{
		`C:\ProgramData\Microsoft\Windows\Certificates\ca-certificates.pem`,
		`C:\Program Files\Docker\Docker\resources\certs`,
		`C:\Program Files\Rancher Desktop\resources\certs`,
		`C:\Users\` + username + `\AppData\Local\Rancher Desktop\certs`,
	}
	for _, path := range windowsCertPaths {
		if fileExists(path) {
			hostCerts = append(hostCerts, path)
		}
	}

	// On macOS: Docker Desktop and Rancher Desktop use system's /etc/ssl/cert.pem
	macCertPaths := []string{
		"/etc/ssl/cert.pem",
		"/usr/local/etc/openssl/cert.pem",
	}
	for _, path := range macCertPaths {
		if fileExists(path) {
			hostCerts = append(hostCerts, path)
		}
	}

	// On Linux: Docker daemon and Rancher Desktop use host's /etc/ssl/certs and system store
	linuxCertPaths := []string{
		"/etc/ssl/certs",
		"/etc/ssl/certs/ca-bundle.crt",
		"/etc/ssl/certs/ca-certificates.crt",
		"/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
		"/etc/rancher/k3s/certs", // Rancher k3s certs
	}
	for _, path := range linuxCertPaths {
		if fileExists(path) {
			hostCerts = append(hostCerts, path)
		}
	}

	return hostCerts
}

// validateCertificatePath checks if a certificate file is readable and valid
func validateCertificatePath(certPath string) error {
	info, err := os.Stat(certPath)
	if err != nil {
		return fmt.Errorf("certificate not accessible: %w", err)
	}

	// If it's a directory, check if it contains any .pem or .crt files
	if info.IsDir() {
		hasValidCerts := false
		filepath.Walk(certPath, func(path string, info os.FileInfo, err error) error {
			if err == nil && !info.IsDir() {
				if strings.HasSuffix(info.Name(), ".pem") || strings.HasSuffix(info.Name(), ".crt") {
					hasValidCerts = true
				}
			}
			return nil
		})
		if !hasValidCerts {
			return fmt.Errorf("directory contains no .pem or .crt files")
		}
		return nil
	}

	// For individual files, verify readability
	data, err := os.ReadFile(certPath)
	if err != nil {
		return fmt.Errorf("cannot read certificate file: %w", err)
	}

	// Basic PEM format check (most common format)
	if !strings.Contains(string(data), "-----BEGIN CERTIFICATE-----") {
		// Could be DER format or bundle - still valid, just warn
		fmt.Printf("   ⚠️  Warning: Certificate may not be in PEM format: %s\n", certPath)
	}

	return nil
}

// runDiagnostics creates a diagnostic container to identify certificate issues
func (cp *CorporatePipeline) runDiagnostics(ctx context.Context, client *dagger.Client) error {
	fmt.Println("\n🔍 DIAGNOSTIC MODE: Analyzing certificate chain...")
	fmt.Println("   This will attempt to connect to critical endpoints and capture certificates")

	const diagnosticImage = "curlimages/curl:latest"

	diagnostic := client.Container().
		From(diagnosticImage).
		WithExec([]string{"sh", "-c", `
set -e

echo "=== System Environment ==="
uname -a
echo ""

echo "=== CA Certificates in Container ==="
if [ -d /etc/ssl/certs ]; then
  ls -la /etc/ssl/certs/ | head -20
else
  echo "No /etc/ssl/certs found"
fi
echo ""

echo "=== Testing docker.io connectivity ==="
curl -v https://registry-1.docker.io/v2/ 2>&1 | head -30 || true
echo ""

echo "=== Testing GitHub Container Registry connectivity ==="
curl -v https://ghcr.io/v2/ 2>&1 | head -30 || true
echo ""

echo "=== Testing Cloudflare R2 CDN (Docker Hub images) ==="
curl -v https://docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com/health 2>&1 | head -30 || true
echo ""

echo "=== Certificate Verification (docker.io) ==="
echo | openssl s_client -servername registry-1.docker.io \
  -connect registry-1.docker.io:443 2>&1 | grep -E "subject=|issuer=|Verify return code" || true
echo ""

echo "=== Certificate Verification (ghcr.io) ==="
echo | openssl s_client -servername ghcr.io \
  -connect ghcr.io:443 2>&1 | grep -E "subject=|issuer=|Verify return code" || true
`})

	output, err := diagnostic.Stdout(ctx)
	if err != nil {
		fmt.Printf("   ⚠️  Diagnostic container had warnings (this is expected)\n")
	}

	fmt.Println("\n=== DIAGNOSTIC OUTPUT ===")
	fmt.Println(output)
	fmt.Println("=== END DIAGNOSTIC OUTPUT ===")

	return nil
}

// collectFromDirectory adds .pem files from a directory
func collectFromDirectory(dir string, discovered map[string]bool, paths *[]string) {
	if !fileExists(dir) {
		return
	}
	files, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, f := range files {
		if !f.IsDir() && strings.HasSuffix(f.Name(), ".pem") {
			fullPath := filepath.Join(dir, f.Name())
			if !discovered[fullPath] {
				*paths = append(*paths, fullPath)
				discovered[fullPath] = true
			}
		}
	}
}

// runCorporate executes the complete CI/CD pipeline with corporate CA support
// runCorporate executes the full Python CI/CD pipeline with corporate CA support.
// Clone → Discover → Build env (with CA certs + proxy) → Unit Tests → Integration Tests
// → Acceptance Tests → Lint → Type-check → Docker Build → Publish.
func (cp *CorporatePipeline) runCorporate(ctx context.Context, client *dagger.Client) error {
	// ── Clone repository ────────────────────────────────────────
	crPAT := client.SetSecret("github-pat", os.Getenv("CR_PAT"))
	gitURL := fmt.Sprintf("https://github.com/%s/%s.git", cp.GitUser, cp.RepoName)
	cp.GitRepo = gitURL
	fmt.Printf("\n📥 Cloning repository: %s (branch: %s)\n", gitURL, cp.GitBranch)

	repo := client.Git(gitURL, dagger.GitOpts{
		KeepGitDir:       true,
		HTTPAuthToken:    crPAT,
		HTTPAuthUsername: "x-access-token",
	})
	source := repo.Branch(cp.GitBranch).Tree()

	commitSHA, err := repo.Branch(cp.GitBranch).Commit(ctx)
	if err != nil {
		return fmt.Errorf("failed to get commit SHA: %w", err)
	}
	fmt.Printf("   Commit: %s\n", commitSHA[:minCorp(12, len(commitSHA))])

	// ── Discover project name from pyproject.toml ────────────────
	fmt.Println("🔍 Discovering project name from pyproject.toml...")
	pyprojectContent, err := source.File("pyproject.toml").Contents(ctx)
	if err != nil {
		return fmt.Errorf("failed to read pyproject.toml: %w", err)
	}
	projectName := extractProjectNameCorp(pyprojectContent)
	if projectName == "" {
		projectName = cp.RepoName
		fmt.Printf("   ⚠️  Could not parse name from pyproject.toml, using repo name: %s\n", projectName)
	} else {
		fmt.Printf("   Project name: %s\n", projectName)
	}
	cp.ProjectName = projectName
	if cp.ImageName == "" {
		cp.ImageName = dockerSafeNameCorp(projectName)
	}

	// ── Check Docker availability for testcontainers ─────────────
	if cp.RunIntegrationTests || cp.RunAcceptanceTests {
		fmt.Println("🔍 Checking Docker availability for testcontainers...")
		if sock := getDockerSocketPathCorp(); sock != "" {
			cp.HasDocker = true
			fmt.Printf("   ✅ Docker socket detected: %s\n", sock)
		} else {
			cp.HasDocker = false
			fmt.Printf("   ⚠️  Docker socket NOT available (OS: %s)\n", runtime.GOOS)
			fmt.Println("   Integration/acceptance tests will be SKIPPED")
		}
	}

	// ── Set up Python build environment with corporate CA + proxy ─
	fmt.Println("🔨 Setting up Python build environment with corporate CA support...")
	cp.PipCache = client.CacheVolume("pip-cache-" + dockerSafeNameCorp(cp.RepoName))
	builder := cp.setupBuildEnv(client, source)

	stageNum := 0

	// ── Stage: Unit Tests (inside Dagger container) ──────────────
	if cp.RunUnitTests {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: UNIT TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Dagger container (isolated, CA certs + proxy configured)")
		fmt.Println("🧪 Running: pytest -m \"not integration and not acceptance\"")
		fmt.Println(corporateSeparatorLine)

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
	if cp.RunIntegrationTests && cp.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: INTEGRATION TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Host machine (testcontainers requires native Docker)")
		fmt.Println("🧪 Running: pytest -v --tb=short -m integration")
		fmt.Println(corporateSeparatorLine)
		if err := cp.runTestsOnHostCorp(ctx, "integration"); err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: INTEGRATION TESTS\n", stageNum)
			return fmt.Errorf("integration tests failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: All integration tests passed\n", stageNum)
	} else if cp.RunIntegrationTests && !cp.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: INTEGRATION TESTS — SKIPPED\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("   ⏭️  Docker not available — testcontainers cannot start PostgreSQL")
	}

	// ── Stage: Acceptance Tests (on host — testcontainers needs Docker) ──
	if cp.RunAcceptanceTests && cp.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: ACCEPTANCE TESTS\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("📍 Location: Host machine (testcontainers requires native Docker)")
		fmt.Println("📦 Fixtures: Real ICAO .bin/.der fixtures used for end-to-end verification")
		fmt.Println("🧪 Running: pytest -v --tb=short -m acceptance")
		fmt.Println(corporateSeparatorLine)
		if err := cp.runTestsOnHostCorp(ctx, "acceptance"); err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: ACCEPTANCE TESTS\n", stageNum)
			return fmt.Errorf("acceptance tests failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: All acceptance tests passed\n", stageNum)
	} else if cp.RunAcceptanceTests && !cp.HasDocker {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: ACCEPTANCE TESTS — SKIPPED\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("   ⏭️  Docker not available — testcontainers cannot start PostgreSQL")
	}

	// ── Stage: Lint ──────────────────────────────────────────────
	if cp.RunLint {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: LINT (ruff)\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("🔍 Running ruff check src/ tests/...")
		lintContainer := builder.WithExec([]string{"ruff", "check", "src/", "tests/"})
		if _, err := lintContainer.Stdout(ctx); err != nil {
			fmt.Printf("\n❌ PIPELINE FAILED AT STAGE %d: LINT\n", stageNum)
			return fmt.Errorf("ruff lint failed: %w", err)
		}
		fmt.Printf("✅ STAGE %d COMPLETE: Lint passed\n", stageNum)
		builder = lintContainer
	}

	// ── Stage: Type Check ────────────────────────────────────────
	if cp.RunTypeCheck {
		stageNum++
		fmt.Printf("\n%s\n", strings.Repeat("=", 80))
		fmt.Printf("PIPELINE STAGE %d: TYPE CHECK (mypy)\n", stageNum)
		fmt.Println(strings.Repeat("=", 80))
		fmt.Println("🔍 Running mypy src/ --strict...")
		typeContainer := builder.WithExec([]string{"mypy", "src/", "--strict"})
		if _, err := typeContainer.Stdout(ctx); err != nil {
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
	imageNameClean := dockerSafeNameCorp(cp.ImageName)
	userLower := strings.ToLower(cp.GitUser)
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
	pubAddr, err := image.
		WithRegistryAuth("ghcr.io", cp.GitUser, password).
		Publish(ctx, versionedImage)
	if err != nil {
		return fmt.Errorf("failed to publish versioned image: %w", err)
	}
	latestAddr, err := image.
		WithRegistryAuth("ghcr.io", cp.GitUser, password).
		Publish(ctx, latestImage)
	if err != nil {
		return fmt.Errorf("failed to publish latest image: %w", err)
	}
	fmt.Printf("✅ STAGE %d COMPLETE: Images published\n", stageNum)
	fmt.Printf("   📦 Versioned: %s\n", pubAddr)
	fmt.Printf("   📦 Latest:    %s\n", latestAddr)

	if deployWebhook := os.Getenv("DEPLOY_WEBHOOK"); deployWebhook != "" {
		fmt.Println("🚀 Triggering deployment webhook...")
		if err := cp.triggerWebhook(deployWebhook, imageTag, pubAddr, commitSHA, timestamp); err != nil {
			fmt.Printf("⚠️  Warning: Deployment trigger failed: %v\n", err)
		} else {
			fmt.Println("✅ Deployment triggered successfully")
		}
	}

	return nil
}

// setupBuildEnv creates a Dagger container with Python build dependencies,
// corporate CA certificates installed, and proxy environment configured.
// Installs: git, build-essential, libpq-dev → upgrades pip → installs
// python_framework (local railway-rop) → installs cert-parser[dev,server].
func (cp *CorporatePipeline) setupBuildEnv(client *dagger.Client, source *dagger.Directory) *dagger.Container {
	container := client.Container().
		From(baseImageCorporate).
		WithExec([]string{"apt-get", "update"}).
		WithExec([]string{"apt-get", "install", "-y", "--no-install-recommends",
			"git", "build-essential", "libpq-dev", "ca-certificates"}).
		WithExec([]string{"rm", "-rf", "/var/lib/apt/lists/*"})

	// Mount corporate CA certificates and update the trust store
	if len(cp.CACertPaths) > 0 {
		fmt.Println("   📜 Mounting corporate CA certificates into container...")
		for _, certPath := range cp.CACertPaths {
			info, err := os.Stat(certPath)
			if err != nil {
				fmt.Printf("   ⚠️  Could not access %s: %v\n", certPath, err)
				continue
			}
			filename := filepath.Base(certPath)
			if info.IsDir() {
				container = container.WithMountedDirectory("/usr/local/share/ca-certificates/"+filename, client.Host().Directory(certPath))
			} else {
				container = container.WithMountedFile("/usr/local/share/ca-certificates/"+filename, client.Host().File(certPath))
			}
			fmt.Printf("      ✓ Mounted %s\n", filename)
		}
		fmt.Println("   🔄 Updating CA certificate store (update-ca-certificates)...")
		container = container.WithExec([]string{"update-ca-certificates"})
	}

	// Configure proxy if present
	if cp.ProxyURL != "" {
		fmt.Println("   🌐 Configuring proxy settings in container...")
		fmt.Printf("      ✓ HTTP_PROXY=%s\n", cp.ProxyURL)
		container = container.
			WithEnvVariable("HTTP_PROXY", cp.ProxyURL).
			WithEnvVariable("HTTPS_PROXY", cp.ProxyURL).
			WithEnvVariable("http_proxy", cp.ProxyURL).
			WithEnvVariable("https_proxy", cp.ProxyURL).
			WithEnvVariable("NO_PROXY", "localhost,127.0.0.1,.local").
			WithEnvVariable("no_proxy", "localhost,127.0.0.1,.local")
	}

	// Also set REQUESTS_CA_BUNDLE to point to the updated system bundle
	// so that Python's requests/httpx library trusts corporate MITM certs
	container = container.
		WithEnvVariable("REQUESTS_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt").
		WithEnvVariable("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt").
		WithEnvVariable("CURL_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")

	// Mount source and install dependencies
	container = container.
		WithMountedCache("/root/.cache/pip", cp.PipCache).
		WithMountedDirectory(appWorkdirCorporate, source).
		WithWorkdir(appWorkdirCorporate).
		WithExec([]string{"pip", "install", "--upgrade", "pip", "setuptools", "wheel"}).
		// Install local framework (railway-rop) before the project
		WithExec([]string{"pip", "install", "-e", "./python_framework"}).
		// Install main project with dev + server extras
		WithExec([]string{"pip", "install", "-e", ".[dev,server]"})

	return container
}

// getRepositorySource clones and returns (directory, commitSHA).
// (Used internally when we need a bare source without the builder setup.)
func (cp *CorporatePipeline) getRepositorySource(ctx context.Context, client *dagger.Client) (*dagger.Directory, string) {
	gitURL := fmt.Sprintf("https://github.com/%s/%s.git", cp.GitUser, cp.RepoName)
	crPAT := client.SetSecret("github-pat", os.Getenv("CR_PAT"))
	repo := client.Git(gitURL, dagger.GitOpts{
		KeepGitDir:       true,
		HTTPAuthToken:    crPAT,
		HTTPAuthUsername: "x-access-token",
	})
	commitSHA, _ := repo.Branch(cp.GitBranch).Commit(ctx)
	return repo.Branch(cp.GitBranch).Tree(), commitSHA
}

// runTestsOnHostCorp executes pytest with a marker on the HOST machine.
// Integration and acceptance tests use testcontainers, which requires native
// Docker socket access — Docker-in-Docker inside Dagger breaks volume mounts.
// The host's corporate proxy env vars are inherited automatically by the child process.
func (cp *CorporatePipeline) runTestsOnHostCorp(ctx context.Context, marker string) error {
	cwd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("failed to get current directory: %w", err)
	}
	projectRoot := cwd + "/.."

	fmt.Println("⚙️  Configuration:")
	fmt.Printf("   • Project root: %s\n", projectRoot)
	fmt.Printf("   • Marker:       %s\n", marker)
	if cp.ProxyURL != "" {
		fmt.Printf("   • Proxy:        %s (inherited from host env)\n", cp.ProxyURL)
	}
	fmt.Println("")

	pytestBin := projectRoot + "/.venv/bin/pytest"
	if _, err := os.Stat(pytestBin); err != nil {
		pytestBin = "pytest"
		fmt.Println("   ⚠️  .venv not found, using system pytest")
	} else {
		fmt.Printf("   • Using: %s\n", pytestBin)
	}

	cmd := exec.CommandContext(ctx, pytestBin, "-v", "--tb=short", "-m", marker)
	cmd.Dir = projectRoot
	cmd.Env = os.Environ() // inherit proxy settings and all host env vars

	var outputBuffer strings.Builder
	multiWriter := io.MultiWriter(os.Stdout, &outputBuffer)
	cmd.Stdout = multiWriter
	cmd.Stderr = os.Stderr

	start := time.Now()
	err = cmd.Run()
	duration := time.Since(start)

	fmt.Println(corporateSeparatorLine)
	cp.displayHostTestSummary(marker, outputBuffer.String(), duration, err)

	if err != nil {
		return fmt.Errorf("%s tests failed: %w", marker, err)
	}
	return nil
}

// displayHostTestSummary parses pytest output and shows a concise result.
func (cp *CorporatePipeline) displayHostTestSummary(marker string, output string, duration time.Duration, testErr error) {
	passedPattern := regexp.MustCompile(`(\d+) passed`)
	failedPattern := regexp.MustCompile(`(\d+) failed`)
	errorPattern := regexp.MustCompile(`(\d+) error`)

	lines := strings.Split(output, "\n")
	var summaryLine string
	for _, line := range lines {
		if strings.Contains(line, "====") &&
			(strings.Contains(line, "passed") || strings.Contains(line, "failed")) {
			summaryLine = line
		}
	}

	label := strings.ToUpper(marker[:1]) + marker[1:]
	fmt.Printf("\n📊 %s Test Summary\n", label)
	fmt.Println(corporateSeparatorLine)

	if summaryLine != "" {
		passed := "0"
		failed := "0"
		errors := "0"
		if m := passedPattern.FindStringSubmatch(summaryLine); m != nil {
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

// ── Self-contained helpers (corporate binary is compiled standalone) ──────────

// extractProjectNameCorp parses the `name = "..."` field from pyproject.toml content.
func extractProjectNameCorp(content string) string {
	re := regexp.MustCompile(`(?m)^name\s*=\s*"([^"]+)"`)
	matches := re.FindStringSubmatch(content)
	if len(matches) >= 2 {
		return matches[1]
	}
	return ""
}

// dockerSafeNameCorp converts a project name to a Docker-safe image name.
func dockerSafeNameCorp(name string) string {
	return strings.ToLower(strings.ReplaceAll(name, "_", "-"))
}

// envOrDefaultCorp returns the value of an environment variable, or a default.
func envOrDefaultCorp(key, defaultValue string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultValue
}

// getDockerSocketPathCorp returns the Docker socket path for the current platform.
// Returns empty string if Docker is not available. Handles Linux, macOS, and Windows.
func getDockerSocketPathCorp() string {
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
	default: // linux
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
		path = strings.TrimPrefix(path, dockerUnixPrefixCorp)
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}
	return ""
}

// minCorp returns the minimum of two integers.
func minCorp(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// triggerWebhook triggers deployment webhook with build metadata
func (cp *CorporatePipeline) triggerWebhook(webhookURL, imageTag, imageAddress, commitSHA, timestamp string) error {
	// This would integrate with your deployment system
	// Example: using webhook to trigger ArgoCD, Flux, or custom deployment service
	fmt.Printf("   Webhook: %s\n", webhookURL)
	fmt.Printf("   Image Tag: %s\n", imageTag)
	fmt.Printf("   Image: %s\n", imageAddress)
	fmt.Printf("   Commit: %s\n", commitSHA)
	fmt.Printf("   Timestamp: %s\n", timestamp)
	return nil
}
