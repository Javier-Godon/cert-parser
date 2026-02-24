# Certificate Discovery Guide for Corporate MITM Environments

## Problem Summary

Your company laptop (Windows 11 managed by company) intercepts HTTPS traffic with custom CA certificates, but Dagger's Go SDK can't verify them because:

1. Dagger engine uses Go's `crypto/x509` verifier (not Docker/system truststore)
2. Corporate CA certificates aren't in the engine's CA bundle
3. The error `x509: certificate signed by unknown authority` occurs when pulling images

## How to Discover Your Corporate Certificates

### Option 1: Extract from Windows Certificate Store (EASIEST)

**On your company Windows 11 laptop:**

1. Open Certificate Manager: `Win + R` → type `certmgr.msc` → Enter
2. Navigate to: `Certificates - Current User` → `Trusted Root Certification Authorities` → `Certificates`
3. Look for **non-standard CAs** (not Microsoft, DigiCert, Let's Encrypt, etc.)
   - Company name CAs
   - Proxy/MITM provider names
   - Internal root CAs
4. For each suspicious CA:
   - Right-click → `All Tasks` → `Export`
   - Choose: `Base-64 encoded X.509 (.CER)`
   - Save to file (e.g., `company-ca.cer`, `proxy-ca.cer`)

**Then convert to PEM:**
```bash
# Copy the .cer files to your Ubuntu machine
# Convert to PEM format
openssl x509 -inform DER -in company-ca.cer -out company-ca.pem
openssl x509 -inform DER -in proxy-ca.cer -out proxy-ca.pem

# Verify the certificate
openssl x509 -in company-ca.pem -text -noout | grep -E "Subject:|Issuer:|Not After"
```

---

### Option 2: Extract from Docker on Company Laptop (if Docker Desktop installed)

**Run this in PowerShell on Windows 11:**

```powershell
# Export trusted certificates from Docker
docker run --rm -v "c:\Program Files\Docker\certs":/certs alpine:latest \
  cat /certs/*/server-ca.crt > company-docker-ca.pem

# OR from Windows certificate store (via Docker)
docker run --rm -it -v c:/Windows/System32/drivers/etc:/certs:ro `
  windows/servercore powershell -c `
  "Get-ChildItem cert:\LocalMachine\Root | ForEach-Object { [IO.File]::WriteAllText(\"cert_$($_.Thumbprint).pem\", $_.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert)) }"
```

---

### Option 3: Extract from Ubuntu on Company Laptop

**On your Ubuntu 24.04 personal laptop (if on company network):**

```bash
# Method 1: Check system CA bundle
ls -la /etc/ssl/certs/
cat /etc/ssl/certs/ca-bundle.crt | grep -A 5 "Subject:" | head -20

# Method 2: Use openssl to connect and capture the certificate chain
echo | openssl s_client -showcerts -servername docker.io -connect docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com:443 2>/dev/null | \
  sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > captured-chain.pem

# Method 3: Check Dagger engine's CA bundle (if available)
docker run --rm registry.dagger.io/engine:v0.19.7 cat /etc/ssl/certs/ca-bundle.crt > engine-ca-bundle.pem

# Method 4: Test with curl and capture the issuer
curl -vvv https://docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com/registry-v2/docker/registry/v2/ 2>&1 | grep -i "cert\|issuer\|subject"
```

---

### Option 4: Diagnose from Current Error

**When you see:**
```
x509: certificate signed by unknown authority
```

**Extract the failing certificate:**

```bash
# Modify your dagger_go/main.go to add diagnostics (see below)
DEBUG_CERTS=true ./run.sh 2>&1 | tee pipeline-debug.log

# This will create a diagnostic container that:
# 1. Lists all CA certificates it has
# 2. Attempts to connect to docker.io
# 3. Shows the certificate chain it receives
```

---

## Certificate Discovery Implementation (for main.go)

Add this diagnostic function to `dagger_go/main.go`:

```go
// discoverCorporateCerts creates a diagnostic container to identify missing CAs
func (p *Pipeline) discoverCorporateCerts(ctx context.Context, client *dagger.Client, debugMode bool) error {
	if !debugMode {
		return nil // Skip if not in debug mode
	}

	fmt.Println("\n🔍 DIAGNOSTIC MODE: Discovering corporate certificates...")
	fmt.Println("   This will attempt to connect to Docker Hub and capture the certificate chain")

	const diagnosticImage = "curlimages/curl:latest"

	diagnostic := client.Container().
		From(diagnosticImage).
		WithExec([]string{"sh", "-c", `
set -ex

echo "=== System CA Certificates ==="
ls -la /etc/ssl/certs/ || echo "No certs found"

echo ""
echo "=== CA Bundle Content (first 50 lines) ==="
head -50 /etc/ssl/certs/ca-bundle.crt || cat /etc/ssl/certs/ca-certificates.crt 2>/dev/null | head -50

echo ""
echo "=== Testing connection to docker.io ==="
curl -v https://registry-1.docker.io/v2/ 2>&1 || true

echo ""
echo "=== Testing connection to Cloudflare R2 CDN ==="
curl -vvv https://docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com/health 2>&1 || true

echo ""
echo "=== OpenSSL certificate chain (docker.io) ==="
echo | openssl s_client -showcerts -servername registry-1.docker.io \
  -connect registry-1.docker.io:443 2>&1 | grep -E "subject=|issuer=|Verify return code" || true

echo ""
echo "=== OpenSSL certificate chain (Cloudflare R2) ==="
echo | openssl s_client -showcerts -servername docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com \
  -connect docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com:443 2>&1 | \
  grep -E "subject=|issuer=|Verify return code" || true
`})

output, err := diagnostic.Stdout(ctx)
if err != nil {
		fmt.Printf("   Note: diagnostic container had warnings (this is OK)\n")
	}

	fmt.Println("\n=== DIAGNOSTIC OUTPUT ===")
	fmt.Println(output)
	fmt.Println("=== END DIAGNOSTIC OUTPUT ===\n")

	return nil
}
```

Add this call to the `run()` method:

```go
// After pipeline initialization
if debugMode {
	if err := p.discoverCorporateCerts(ctx, client, debugMode); err != nil {
		fmt.Printf("⚠️  Certificate discovery had issues: %v\n", err)
		// Continue anyway - this is just diagnostic
	}
}
```

---

## Step-by-Step Certificate Collection Process

### 1. **Identify All Failing Endpoints** (Run diagnostics first)

```bash
cd dagger_go
DEBUG_CERTS=true ./run.sh 2>&1 | grep -i "certificate\|x509\|issuer" | tee cert-errors.log
```

### 2. **Document What You Find**

Create a `CERTIFICATES_FOUND.md` in your credentials folder:

```markdown
# Corporate Certificates Identified

## Certificate 1: Company Proxy CA
- **Subject**: CN=Company-Proxy-Root, O=Company Inc, C=US
- **Issuer**: CN=Company-Proxy-Root (self-signed)
- **Thumbprint**: A1B2C3D4E5F6...
- **Scope**: Intercepts all HTTPS traffic
- **File**: company-proxy-ca.pem

## Certificate 2: Internal Root CA
- **Subject**: CN=Company-Internal-Root, O=Company Inc, C=US
- **Issuer**: CN=Company-Internal-Root (self-signed)
- **Scope**: Internal services only
- **File**: company-internal-ca.pem

## Affected Endpoints
- docker.io (Docker Hub)
- ghcr.io (GitHub Container Registry)
- *.r2.cloudflarestorage.com (Docker Hub CDN)
- pypi.org (if using Python)
```

### 3. **Add to Credentials**

```bash
# Create certificates directory
mkdir -p credentials/certs

# Copy your extracted certificates
cp /path/to/company-ca.pem credentials/certs/
cp /path/to/proxy-ca.pem credentials/certs/

# Verify they're readable
ls -lh credentials/certs/
```

### 4. **Store in credentials/.env**

```bash
cat >> credentials/.env << 'EOF'

# Corporate Certificate Paths (relative to workspace root)
CERT_COMPANY_PROXY=credentials/certs/company-proxy-ca.pem
CERT_COMPANY_INTERNAL=credentials/certs/company-internal-ca.pem
CERT_BUNDLE=credentials/certs/ca-bundle.pem
EOF
```

---

## Quick Commands to Capture Certificates

### From Windows (PowerShell):

```powershell
# Export all trusted root CAs
Get-ChildItem cert:\CurrentUser\Root | ForEach-Object {
    $cert = $_
    $path = "C:\Temp\certs\$($cert.Thumbprint).cer"
    [IO.File]::WriteAllBytes($path, $cert.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    Write-Host "Exported: $($cert.Subject) -> $path"
}
```

### From Linux/Ubuntu:

```bash
# Extract from system
sudo cp /etc/ssl/certs/ca-bundle.crt ~/company-ca-bundle.pem

# Extract from environment variable (if set by company)
echo $SSL_CERT_FILE  # Check if company sets this

# Extract from curl
curl -vvv https://docker.io 2>&1 | grep -i "subject:"
```

### From Docker:

```bash
# If Docker on company network has the certs
docker run --rm alpine:latest apk add --no-cache ca-certificates && \
  docker run --rm -v /etc/ssl/certs:/certs:ro alpine:latest \
  cat /certs/ca-bundle.crt > docker-system-ca.pem
```

---

## What You're Looking For

- **Company/Organization name** in certificate subject
- **Proxy provider names** (e.g., "Blue Coat", "Fortinet", "Zscaler")
- **"Man-in-the-Middle"** or **"Intercepting Proxy"** in description
- **Non-standard root CAs** that aren't in Mozilla's trust store
- **Timestamps** showing installation date (usually before you started having issues)

---

## Next Steps Once You Find Certificates

1. Create `credentials/certs/` directory
2. Place all `.pem` files there
3. Create a `.gitignore` entry to prevent accidental commit:
   ```bash
   echo "credentials/certs/*.pem" >> .gitignore
   ```
4. Update `dagger_go/main.go` to mount certificates (I can help with this)
5. Test with: `DEBUG_CERTS=true ./run.sh`

---

## Troubleshooting Certificate Collection

| Symptom | Solution |
|---------|----------|
| Can't access Windows cert store | Run `certmgr.msc` as Administrator |
| Certificate export shows "0 bytes" | Export as "Base-64 encoded X.509 (.CER)" format |
| OpenSSL can't read the file | Convert: `openssl x509 -inform DER -in file.cer -out file.pem` |
| Too many certificates to check | Filter: grep -i "company\|proxy\|root" |
| Still getting x509 errors after adding certs | Certificate may be in a chain - you need the full chain |

---

## Resources

- [Exporting Certificates from Windows](https://docs.microsoft.com/en-us/windows/win32/seccrypto/about-certificates)
- [OpenSSL certificate inspection](https://www.openssl.org/docs/man1.1.1/man1/openssl-x509.html)
- [Docker Dagger Custom CA support](https://github.com/dagger/dagger/issues/6599)
- [x509 certificate errors explanation](https://pkg.go.dev/crypto/x509)
