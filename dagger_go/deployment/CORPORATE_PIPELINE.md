# Corporate Pipeline — MITM Proxy & Custom CA Support

Complete guide to using the corporate version of the cert-parser Python CI/CD pipeline with custom certificate authority and proxy support.

## Overview

The **corporate pipeline** is a separate implementation that adds support for:

- ✅ **Custom CA Certificates** - Handle corporate MITM proxies
- ✅ **HTTP/HTTPS Proxies** - Route traffic through corporate proxies
- ✅ **Certificate Diagnostics** - Identify what certificates are needed
- ✅ **Fully Isolated** - Your working `main.go` is 100% untouched

### File Structure

```
dagger_go/
├── main.go                 # ← Original working pipeline (UNCHANGED)
├── corporate_main.go       # ← New corporate version (added)
├── run.sh                  # ← Original script (UNCHANGED)
├── run-corporate.sh        # ← New corporate script (added)
└── cert-parser-dagger-go       # Binary (either version)
```

---

## Quick Start: Using Corporate Pipeline

### Step 1: Prepare Credentials Directory

```bash
# Ensure directories exist
mkdir -p credentials/certs

# Edit credentials/.env to add proxy settings
cat >> credentials/.env << 'EOF'

# Proxy settings (optional - only if you have a proxy)
HTTP_PROXY=http://proxy.company.com:8080
HTTPS_PROXY=https://proxy.company.com:8080
NO_PROXY=localhost,127.0.0.1,.local

# Or use environment variables from command line
EOF
```

### Step 2: Add CA Certificates (if needed)

```bash
# Copy your extracted .pem files to credentials/certs/
cp /path/to/company-ca.pem credentials/certs/
cp /path/to/proxy-ca.pem credentials/certs/

# Verify they're there
ls -lh credentials/certs/
```

### Step 3: Run Corporate Pipeline

```bash
cd dagger_go

# Option A: Normal run
set -a && source ../credentials/.env && set +a
./run-corporate.sh

# Option B: With certificate diagnostics
DEBUG_CERTS=true ./run-corporate.sh

# Option C: With verbose output
set -a && source ../credentials/.env && set +a
DEBUG_CERTS=true ./run-corporate.sh 2>&1 | tee corporate-pipeline.log
```

---

## What Gets Added (Corporate Version)

### ✅ Corporate Pipeline Features

```
From: docker.io
      ↓
   [X] Certificate error: x509: certificate signed by unknown authority
   [X] Proxy blocks connection
   [X] Unable to pull eclipse-temurin image

After: Corporate Pipeline
      ↓
   [✓] Custom CA certificates mounted in container
   [✓] Proxy configured (HTTP_PROXY environment variables)
   [✓] pip/Python configured for proxy (REQUESTS_CA_BUNDLE, SSL_CERT_FILE)
   [✓] Docker images pull successfully
```

### File: `corporate_main.go` (~1200 lines)

**Key Type:**
```go
type CorporatePipeline struct {
    RepoName            string
    ProjectName         string   // Discovered from pyproject.toml
    ImageName           string
    GitRepo             string
    GitBranch           string
    GitUser             string
    PipCache            *dagger.CacheVolume
    HasDocker           bool
    RunUnitTests        bool
    RunIntegrationTests bool
    RunAcceptanceTests  bool
    RunLint             bool
    RunTypeCheck        bool
    CACertPaths         []string  // Paths to CA certificates
    ProxyURL            string    // HTTP proxy URL
    DebugMode           bool      // Enable certificate diagnostics
}
```

**Key Functions:**
- `main()` — entry point; reads env vars; initialises `CorporatePipeline`; calls `runCorporate()`
- `collectCACertificates()` — auto-discovers `.pem`/`.crt` files from 50+ locations
- `runDiagnostics()` — spins up a `curlimages/curl` container to diagnose TLS issues
- `(cp) setupBuildEnv()` — builds the Python container with CA certs mounted + proxy vars set
- `(cp) runCorporate()` — main 7-stage pipeline (clone → tests → lint → type-check → build → push)

**What It Does:**
1. Collects CA certificate paths from multiple sources (ordered by priority)
2. Creates a Python 3.14-slim Dagger container with certs mounted in `/usr/local/share/ca-certificates/`
3. Runs `update-ca-certificates` to register them with the OS trust store
4. Sets `HTTP_PROXY`, `HTTPS_PROXY`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` env vars
5. Installs `python_framework` then `cert-parser[dev,server]` using pip (now proxy-aware)
6. Runs all 7 pipeline stages with the prepared container

---

## Usage Examples

### Example 1: Simple Corporate Setup

```bash
cd dagger_go

# Add your CA certificate
cp ~/company-root-ca.pem credentials/certs/

# Run with proxy
cat >> credentials/.env << EOF
HTTP_PROXY=http://proxy.company.com:8080
HTTPS_PROXY=https://proxy.company.com:8080
EOF

# Execute
./run-corporate.sh
```

### Example 2: Diagnose Certificate Issues

```bash
cd dagger_go

# Run with diagnostics to see what certificates are needed
DEBUG_CERTS=true ./run-corporate.sh 2>&1 | tee diagnostics.log

# Check output for certificate chain information:
# === OpenSSL Certificate Chain (docker.io) ===
# subject=CN=...
# issuer=CN=...
# Verify return code: 20 (unable to get local issuer certificate)
```

### Example 3: Multiple Corporate CAs

```bash
# Add all your company certificates
cp company-root-ca.pem credentials/certs/
cp company-intermediate-ca.pem credentials/certs/
cp proxy-mitm-ca.pem credentials/certs/

# Run - it will mount all of them
./run-corporate.sh

# Output shows:
# Found 3 CA certificate(s)
# - company-root-ca.pem
# - company-intermediate-ca.pem
# - proxy-mitm-ca.pem
```

### Example 4: Switch Between Versions

```bash
# Use ORIGINAL working pipeline (no changes)
set -a && source ../credentials/.env && set +a
./run.sh

# Use CORPORATE pipeline (with CA/proxy support)
set -a && source ../credentials/.env && set +a
./run-corporate.sh

# Both work independently - no interference
```

---

## How Certificate Mounting Works

### Inside the Corporate Pipeline (`setupBuildEnv()`)

```go
// For each CA certificate path discovered:
for _, certPath := range cp.CACertPaths {
    filename := filepath.Base(certPath)
    info, _ := os.Stat(certPath)
    if info.IsDir() {
        container = container.WithMountedDirectory(
            "/usr/local/share/ca-certificates/"+filename,
            client.Host().Directory(certPath),
        )
    } else {
        container = container.WithMountedFile(
            "/usr/local/share/ca-certificates/"+filename,
            client.Host().File(certPath),
        )
    }
}
// Register them with the OS trust store (Debian/Ubuntu)
container = container.WithExec([]string{"update-ca-certificates"})
```

### Inside the Build Container (python:3.14-slim)

```
Container: python:3.14-slim
├── /usr/local/share/ca-certificates/
│   ├── company-root-ca.pem    (YOUR CA — mounted from host)
│   └── proxy-mitm-ca.pem      (YOUR CA — mounted from host)
├── /etc/ssl/certs/
│   └── ca-certificates.crt    (updated by update-ca-certificates)
└── /app/                      (cert-parser source + venv)

Environment Variables:
├── HTTP_PROXY=http://proxy.company.com:8080
├── HTTPS_PROXY=https://proxy.company.com:8080
├── http_proxy=http://proxy.company.com:8080
├── https_proxy=http://proxy.company.com:8080
├── NO_PROXY=localhost,127.0.0.1,.local
├── REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
├── SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
└── CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

---

## Troubleshooting

### Issue 1: "Found 0 CA certificate(s)"

**Problem**: No certificates mounted
```
⚠️  No CA certificates found in credentials/certs/
```

**Solution**:
```bash
# Create directory
mkdir -p credentials/certs

# Copy your .pem files
cp company-ca.pem credentials/certs/

# Verify
ls credentials/certs/
```

### Issue 2: Still Getting x509 Errors

**Problem**: Certificates mounted but still failing
```
x509: certificate signed by unknown authority
```

**Solutions**:

A) **Run diagnostics to see what's needed:**
```bash
DEBUG_CERTS=true ./run-corporate.sh 2>&1 | grep -A 10 "Certificate Chain"
```

B) **Check certificate format:**
```bash
# Must be PEM format (text, starts with -----BEGIN CERTIFICATE-----)
file credentials/certs/*.pem
cat credentials/certs/company-ca.pem | head -3
```

C) **You might need the full chain:**
```bash
# Extract full chain from failing connection
echo | openssl s_client -showcerts -servername registry-1.docker.io \
  -connect registry-1.docker.io:443 2>&1 | \
  sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > full-chain.pem

cp full-chain.pem credentials/certs/
```

### Issue 3: Proxy Not Working

**Problem**: Certificates work but proxy isn't being used
```
DEBUG_CERTS=true ./run-corporate.sh
# Shows proxy options but connections still go direct
```

**Solution**:

A) **Verify proxy setting:**
```bash
cat credentials/.env | grep PROXY
```

B) **Set proxy in command line:**
```bash
HTTP_PROXY=http://proxy.company.com:8080 \
HTTPS_PROXY=https://proxy.company.com:8080 \
./run-corporate.sh
```

C) **Verify proxy is actually needed:**
```bash
# Test if you can reach docker.io directly
docker run --rm curlimages/curl curl -I https://registry-1.docker.io/v2/

# If this works, you don't need proxy
# If it fails with certificate error, you need proxy + CA
```

### Issue 4: "Certificate Verify Failed"

**Problem**: Proxy CA not trusted
```
curl: (60) SSL certificate problem: self signed certificate in chain
```

**Root Cause**: Your proxy's MITM certificate isn't in the container

**Solution**:
```bash
# Extract proxy certificate
echo | openssl s_client -servername any-host.com \
  -connect proxy.company.com:3128 2>&1 | \
  openssl x509 > proxy-cert.pem

cp proxy-cert.pem credentials/certs/

./run-corporate.sh
```

---

## Environment Variables Reference

### Required
```bash
CR_PAT=ghp_your_github_token        # GitHub Personal Access Token
USERNAME=your_github_username       # GitHub username
```

### Optional - Proxy Configuration
```bash
HTTP_PROXY=http://proxy.company.com:8080
HTTPS_PROXY=https://proxy.company.com:8080
NO_PROXY=localhost,127.0.0.1,.local,company.internal
```

### Optional - Pipeline Configuration
```bash
REPO_NAME=cert-parser     # Repository name
GIT_REPO=https://github.com/...     # Full git URL
GIT_BRANCH=main                      # Branch to build
IMAGE_NAME=cert-parser    # Docker image name
DEPLOY_WEBHOOK=https://...          # Deployment webhook (optional)
```

### Debug Modes
```bash
DEBUG_CERTS=true                    # Enable certificate diagnostics
```

---

## Original Pipeline Untouched

### What Does NOT Change

Your original `main.go` is 100% protected:

```bash
# Original pipeline still works exactly the same
./run.sh

# No changes to these files:
# ✓ main.go (original)
# ✓ run.sh (original)
# ✓ cert-parser-dagger-go binary
```

### Switching Between Versions

```bash
# Use original
./run.sh                  # Uses original main.go + run.sh

# Use corporate
./run-corporate.sh       # Uses corporate_main.go (with special build wrapper)

# Both can run independently without interfering
```

---

## File Layout Reference

```
dagger_go/
├── main.go                              ← Standard pipeline (~572 lines)
│   ├── type Pipeline struct
│   ├── func main() — standard entry point
│   ├── func (p *Pipeline) run() — 7-stage pipeline
│   ├── func (p *Pipeline) runTestsOnHost() — host-based pytest
│   └── helpers: extractProjectName, dockerSafeName, parseEnvBool, ...
│
├── corporate_main.go                    ← Corporate variant (~1200 lines)
│   ├── //go:build corporate             ← prevents double-main conflict
│   ├── type CorporatePipeline struct
│   ├── func main() — corporate entry point
│   ├── func collectCACertificates() — 50+ location auto-discovery
│   ├── func (cp) setupBuildEnv() — mounts CA certs + proxy
│   ├── func (cp) runCorporate() — 7-stage pipeline with CA/proxy
│   ├── func (cp) runDiagnostics() — TLS connectivity test via curlimages/curl
│   ├── func (cp) runTestsOnHostCorp() — host pytest (inherits proxy env)
│   └── helpers: extractProjectNameCorp, dockerSafeNameCorp, ...
│
├── run.sh                               ← Standard runner
│   └── go build -o cert-parser-dagger-go main.go
│
├── run-corporate.sh                     ← Corporate runner
│   └── go build -tags corporate -o cert-parser-corporate-dagger-go corporate_main.go
│
├── cert-parser-dagger-go                ← Standard binary
└── cert-parser-corporate-dagger-go      ← Corporate binary
```

---

## Advanced: Custom Certificate Validation

### Monitor What Certificates Are Being Used

```bash
# Run with diagnostics and save output
DEBUG_CERTS=true ./run-corporate.sh 2>&1 | tee corporate-run.log

# Extract certificate information
grep -A 5 "Certificate Chain" corporate-run.log
grep "subject=" corporate-run.log
grep "issuer=" corporate-run.log
grep "Verify return code" corporate-run.log
```

### Validate Certificate Format

```bash
# Check if certificate is valid
openssl x509 -in credentials/certs/company-ca.pem -text -noout | head -20

# Should show:
# Certificate:
#     Data:
#         Version: 3 (0x2)
#         Serial Number: ...
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN = Company Root CA, ...
```

---

## Comparison: Original vs Corporate

| Feature | Original | Corporate |
|---------|----------|-----------|
| **Functionality** | Full CI/CD | Full CI/CD + Corporate |
| **Custom CAs** | ❌ | ✅ |
| **Proxy Support** | ❌ | ✅ |
| **Diagnostics** | ❌ | ✅ (optional) |
| **File Size** | ~170 lines | ~350 lines total |
| **Complexity** | Simple | Advanced |
| **Corporate MITM** | ❌ Fails | ✅ Works |
| **Personal Laptop** | ✅ Works | ✅ Works (extra setup) |

---

## Migration Path

### If Original Pipeline Works (Personal Laptop)
- Keep using `./run.sh`
- No need for corporate pipeline
- You're good! ✅

### If Original Pipeline Fails (Company Laptop)
- Try `./run-corporate.sh` instead
- Run with `DEBUG_CERTS=true` first
- Extract certificates from the diagnostics
- Add to `credentials/certs/`
- Re-run
- Should work! ✅

---

## Support & Documentation

For more information:

- 📄 **Certificate Discovery**: See `CERTIFICATE_DISCOVERY.md`
- 📋 **Build & Run**: See `BUILD_AND_RUN.md`
- 🚀 **Quick Start**: See `QUICKSTART.md`
- 📊 **Architecture**: See `README.md`

---

## Next Steps

1. ✅ Copy `.pem` files to `credentials/certs/`
2. ✅ Add proxy settings to `credentials/.env`
3. ✅ Run: `./run-corporate.sh`
4. ✅ If issues, run: `DEBUG_CERTS=true ./run-corporate.sh`
5. ✅ Check logs for certificate chain information

---

**Status**: ✅ Ready to use
**Last Updated**: March 2026
**Standard Pipeline**: Completely untouched — `main.go` and `run.sh` are never modified
