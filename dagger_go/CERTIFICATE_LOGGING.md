# Certificate Discovery Detailed Logging

## Overview

The corporate pipeline now includes comprehensive logging for certificate discovery operations. Enable with `DEBUG_CERTS=true` to see detailed information about every certificate source checked.

## Usage

```bash
# Enable detailed certificate logging
export DEBUG_CERTS=true
cd dagger_go
./run-corporate.sh
```

## Log Output Format

### Summary View (Default)
```
🏢 CORPORATE MODE: MITM Proxy & Custom CA Support
   🔍 Debug mode: ENABLED - Certificate discovery active
   📜 Found 2 CA certificate path(s)
      - ca-certificates.crt ✅
      - certs ✅
```

### Detailed View (DEBUG_CERTS=true)
```
📜 Certificate Discovery - Detailed Log
─────────────────────────────────────────────────────────────────────────────────

🔍 Source: User-provided certificates (credentials/certs/)
   ℹ️  Directory not found (this is optional)

🔍 Source: System certificate stores (50+ locations)
   ✅ Found: /etc/ssl/certs/ca-certificates.crt
   ✅ Found: /etc/ssl/certs

🔍 Source: Docker/Rancher Desktop directories (recursive scan)
   🔍 Scanning: /home/user/.docker/certs.d
      ✅ /home/user/.docker/certs.d/docker.io/ca.pem
      ✅ /home/user/.docker/certs.d/ghcr.io/ca.pem
   📊 Found 2 certificate(s) in this directory
   ℹ️  Directory not found: /etc/docker/certs.d
   ℹ️  No Docker/Rancher certificates found (directories may not exist or be empty)

🔍 Source: Docker host system certificates
   ✅ Found: /etc/ssl/certs

🔍 Source: CA_CERTIFICATES_PATH environment variable
   🔍 Checking paths: /custom/certs:/other/certs
   ✅ Found: /custom/certs
   ❌ Not found: /other/certs

🔍 Source: Jenkins CI/CD environment
   🏢 Jenkins detected: /var/jenkins_home
   ✅ Found: /var/jenkins_home/war/WEB-INF/ca-bundle.crt
   ⚠️  Jenkins detected but no certificates found in standard locations

🔍 Source: GitHub Actions runner environment
   🐙 GitHub Actions detected: /home/runner/work/_temp
   ✅ Found: /home/runner/work/_temp/ca-certificates

📊 Certificate Discovery Summary
─────────────────────────────────────────────────────────────────────────────────
   🔍 Total sources checked: 37
   ✅ Certificates found: 6
   ℹ️  Not found: 31
   ❌ Errors: 0
   📜 Unique certificates collected: 6
─────────────────────────────────────────────────────────────────────────────────
```

## Log Indicators

| Symbol | Meaning |
|--------|---------|
| ✅ | Certificate or directory found successfully |
| ❌ | Error accessing path or certificate not found |
| ⚠️ | Warning - expected location exists but no certificates found |
| ℹ️ | Informational - location doesn't exist (normal) |
| 🔍 | Currently scanning/checking location |
| 📊 | Statistics or summary information |
| 🏢 | Jenkins CI/CD environment detected |
| 🐙 | GitHub Actions environment detected |
| 📜 | Certificate-related information |

## Discovery Sources Tracked

1. **User-provided certificates** (`credentials/certs/`)
   - Shows each `.pem` file found
   - Indicates if directory doesn't exist

2. **System certificate stores** (50+ locations)
   - Linux: `/etc/ssl/certs/`, `/etc/pki/ca-trust/`
   - macOS: `/etc/ssl/cert.pem`, `/usr/local/etc/openssl/`
   - Windows: `C:\ProgramData\Microsoft\Windows\Certificates\`
   - Shows each found location

3. **Docker/Rancher Desktop directories** (recursive scan)
   - Shows directory scan progress
   - Lists each certificate file found
   - Reports total certificates per directory

4. **Docker host system certificates**
   - Platform-specific inherited certificates
   - Shows each host certificate path

5. **CA_CERTIFICATES_PATH environment variable**
   - Shows the full path list being checked
   - Reports each found/not-found path

6. **Jenkins CI/CD environment**
   - Detects `$JENKINS_HOME`
   - Shows Jenkins-specific certificate locations

7. **GitHub Actions runner**
   - Detects `$RUNNER_TEMP`
   - Shows GitHub Actions custom certificates

## Statistics

The summary provides:
- **Total sources checked**: Number of discovery sources attempted (37 in standard configuration)
- **Certificates found**: Successfully discovered certificate paths
- **Not found**: Locations that don't exist (expected on different platforms)
- **Errors**: Access errors or read failures (troubleshoot if > 0)
- **Unique certificates collected**: Final deduplicated count

## Troubleshooting

### No Certificates Found

```
📊 Certificate Discovery Summary
   🔍 Total sources checked: 37
   ✅ Certificates found: 0
   ℹ️  Not found: 37
```

**Solutions**:
1. Place `.pem` files in `credentials/certs/`
2. Set `CA_CERTIFICATES_PATH=/path/to/your/certs`
3. Verify corporate certificates are installed system-wide

### Errors Reported

```
📊 Certificate Discovery Summary
   ❌ Errors: 5
```

**Investigation**:
1. Check file permissions on certificate directories
2. Verify paths exist and are readable
3. Look for "❌ Error reading directory" messages in detailed log
4. Review error messages for specific permission issues

### Platform-Specific

**Linux**: Should find `/etc/ssl/certs/ca-certificates.crt` by default

**macOS**: Should find `/etc/ssl/cert.pem` and Docker Desktop Group Containers

**Windows**: Should find `C:\ProgramData\Microsoft\Windows\Certificates\`

**WSL**: Should find `/mnt/c/ProgramData/Microsoft/Windows/Certificates/`

## CI/CD Integration

### Jenkins Example

```groovy
pipeline {
    environment {
        DEBUG_CERTS = 'true'  // Enable detailed logging
        CA_CERTIFICATES_PATH = "${JENKINS_HOME}/corporate-certs"
    }
    stages {
        stage('Build') {
            steps {
                sh 'cd dagger_go && ./run-corporate.sh'
            }
        }
    }
}
```

### GitHub Actions Example

```yaml
- name: Corporate Build
  env:
    DEBUG_CERTS: 'true'
    CA_CERTIFICATES_PATH: ${{ github.workspace }}/certs
  run: cd dagger_go && ./run-corporate.sh
```

## Performance Impact

- **Default mode** (DEBUG_CERTS=false): Minimal overhead, only summary statistics
- **Debug mode** (DEBUG_CERTS=true): ~50-100ms additional time for logging
- Certificate discovery itself: ~100-200ms (same with or without debug logging)

## Security Considerations

✅ **Safe Information Logged**:
- Certificate file paths
- Directory existence checks
- Source detection (Jenkins, GitHub Actions)
- Statistics and counts

❌ **NOT Logged** (secure):
- Certificate contents (secured via `WithMountedFile` instead of `WithNewFile`)
- Private keys
- Proxy URLs (only "Proxy: configured" message)
- Authentication tokens (CR_PAT stored as Dagger Secret)

⚠️ **Partial Logging** (Dagger API limitation):
- GitHub usernames appear in `WithRegistryAuth` logs
- This is unavoidable - Dagger's API requires username as string, not Secret
- Risk is low (usernames are typically public in GitHub URLs)
- Password/token remains protected as Secret (never logged)

### Certificate Content Protection

**Fixed in v1.1.0**: Certificates are now mounted securely:

```go
// ❌ OLD (insecure - exposed content in logs):
certData, err := ioutil.ReadFile(certPath)
container = container.WithNewFile("/etc/ssl/certs/ca.crt", string(certData))
// Result: Dagger logs full certificate content as parameter

// ✅ NEW (secure - no content exposure):
container = container.WithMountedFile("/etc/ssl/certs/ca.crt", client.Host().File(certPath))
// Result: Dagger logs only file path, not contents
```

**Diagnostic Mode Security**: The `-showcerts` flag was removed from `openssl s_client` commands to prevent certificate content from appearing in diagnostic logs. Only metadata (subject, issuer, validation status) is now displayed.

The logging is safe for CI/CD logs and does not expose sensitive information.

## Related Documentation

- [CERTIFICATE_QUICK_REFERENCE.md](./CERTIFICATE_QUICK_REFERENCE.md) - User guide for certificate setup
- [.github/instructions/dagger-certificate-implementation.instructions.md](../.github/instructions/dagger-certificate-implementation.instructions.md) - Technical implementation details
- [QUICKSTART.md](./QUICKSTART.md) - Getting started with the pipeline

---

**Last Updated**: November 27, 2025
**Status**: ✅ Production Ready
