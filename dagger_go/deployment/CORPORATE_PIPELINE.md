# Corporate Pipeline - MITM Proxy & Custom CA Support

Complete guide to using the corporate version of the Railway-Oriented Java CI/CD pipeline with custom certificate authority and proxy support.

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
   [✓] Maven configured for proxy
   [✓] Docker images pull successfully
```

### File: `corporate_main.go` (130+ lines)

**New Types:**
```go
type CorporatePipeline struct {
    *RailwayPipeline         // Inherits original pipeline
    CACertPaths []string     // Paths to CA .pem files
    ProxyURL    string       // Proxy URL (http://proxy.com:8080)
    DebugMode   bool         // Enable diagnostics
}
```

**New Functions:**
- `corporateMain()` - Entry point (calls corporate pipeline)
- `collectCACertificates()` - Finds all .pem files in credentials/certs/
- `runDiagnostics()` - Creates diagnostic container
- `runCorporate()` - Main pipeline with CA/proxy support

**What It Does:**
1. Collects all .pem files from `credentials/certs/`
2. Mounts them into build containers
3. Updates CA certificate store in container
4. Configures HTTP_PROXY/HTTPS_PROXY if set
5. Runs test → build → dockerize → publish

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

### Inside the Corporate Pipeline

```go
// For each .pem file in credentials/certs/
for _, certPath := range cp.CACertPaths {
    certData, _ := ioutil.ReadFile(certPath)

    // Mount to container
    containerPath := fmt.Sprintf("/etc/ssl/certs/%s", filepath.Base(certPath))
    setupContainer = setupContainer.WithNewFile(containerPath, string(certData))
}

// Update CA certificate store
setupContainer = setupContainer.WithExec([]string{"bash", "-c", `
    # Detect OS and update accordingly
    if command -v update-ca-certificates; then
        update-ca-certificates  # Debian/Ubuntu
    elif command -v update-ca-trust; then
        update-ca-trust          # RHEL/Amazon Linux
    fi
`})
```

### Inside Build Container

```
Container: amazoncorretto:25.0.1
├── /etc/ssl/certs/
│   ├── ca-bundle.crt          (system CAs)
│   ├── company-root-ca.pem    (YOUR CA)
│   ├── proxy-mitm-ca.pem      (YOUR CA)
│   └── ...
└── /root/.m2/                 (Maven cache)

Environment Variables:
├── HTTP_PROXY=http://proxy.company.com:8080
├── HTTPS_PROXY=https://proxy.company.com:8080
├── NO_PROXY=localhost,127.0.0.1,.local
└── [Maven inherits these automatically]
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
├── main.go
│   ├── RailwayPipeline type
│   ├── main() function (ORIGINAL)
│   ├── run() method
│   └── [170 lines - UNCHANGED]
│
├── corporate_main.go (NEW)
│   ├── CorporatePipeline type (extends RailwayPipeline)
│   ├── corporateMain() function
│   ├── collectCACertificates() - NEW
│   ├── runDiagnostics() - NEW
│   ├── runCorporate() method - NEW
│   └── [180+ lines - ADDED]
│
├── run.sh (ORIGINAL)
│   └── Uses `go build -o cert-parser-dagger-go main.go`
│
├── run-corporate.sh (NEW)
│   ├── Temporarily renames main.go
│   ├── Creates wrapper main() calling corporateMain()
│   ├── Compiles: `go build -o cert-parser-dagger-go main.go corporate_main.go`
│   ├── Restores original main.go
│   └── Runs binary
│
└── cert-parser-dagger-go (binary - either version)
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
**Last Updated**: November 22, 2025
**Original Pipeline**: Completely untouched
