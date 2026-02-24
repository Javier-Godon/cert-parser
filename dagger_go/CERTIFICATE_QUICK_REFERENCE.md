# Corporate Certificate Support - User Guide

## Quick Start

Place your corporate CA certificates in `credentials/certs/` and run the pipeline:

```bash
mkdir -p credentials/certs
cp /path/to/corporate-ca.pem credentials/certs/
./cert-parser-corporate-dagger-go
```

The pipeline automatically discovers certificates from system stores, Docker/Rancher, and CI/CD environments (Jenkins, GitHub Actions).

## Debug Mode

```bash
export DEBUG_CERTS=true
./cert-parser-corporate-dagger-go
```

## Automatic Discovery Locations

**User Certificates**: `credentials/certs/*.pem` (highest priority)

**Linux**: `/etc/ssl/certs/ca-certificates.crt`, `/etc/docker/certs.d/`, `~/.docker/certs.d/`

**macOS**: `/etc/ssl/cert.pem`, `~/.docker/certs.d/`, `~/Library/Group Containers/group.com.docker/certs`

**Windows**: `C:\ProgramData\Microsoft\Windows\Certificates\`, `C:\Users\<user>\.docker\certs.d\`

**Jenkins**: `$JENKINS_HOME/war/WEB-INF/ca-bundle.crt`, `$JENKINS_HOME/certs`

**GitHub Actions**: `$RUNNER_TEMP/ca-certificates/`

## Environment Variables

**CA_CERTIFICATES_PATH**: Override discovery (colon-separated paths)
```bash
export CA_CERTIFICATES_PATH=/custom/path/ca-bundle.pem:/another/path
```

**DEBUG_CERTS**: Enable detailed logging
```bash
export DEBUG_CERTS=true
./cert-parser-corporate-dagger-go
```

**Output**:
```
📜 Found 3 CA certificate path(s)
   - corporate-root-ca.pem ✅
   - /etc/ssl/certs/ca-certificates.crt ✅
   - ~/.docker/certs.d ✅
```

### HTTP_PROXY / HTTPS_PROXY

Configure corporate proxy (auto-detected):

```bash
export HTTPS_PROXY=http://proxy.company.com:8080
./cert-parser-corporate-dagger-go
```

**HTTP_PROXY/HTTPS_PROXY**: Proxy configuration (auto-detected)
```bash
export HTTPS_PROXY=http://proxy.company.com:8080
```

## CI/CD Integration

### Jenkins
```groovy
pipeline {
    stages {
        stage('Build') {
            steps { sh './cert-parser-corporate-dagger-go' }
        }
    }
}
```

### GitHub Actions
```yaml
jobs:
  build:
    steps:
      - name: Setup Certificates
        run: |
          mkdir -p ${{ runner.temp }}/ca-certificates
          echo "${{ secrets.CORPORATE_CA }}" > ${{ runner.temp }}/ca-certificates/corporate-ca.pem
      - run: ./cert-parser-corporate-dagger-go
```

## Troubleshooting

**No certificates found**:
```bash
# Place manually or use environment variable
mkdir -p credentials/certs && cp /path/to/ca.pem credentials/certs/
export CA_CERTIFICATES_PATH=/path/to/ca-bundle.pem
```

**Permission issues**:
```bash
chmod 644 credentials/certs/*.pem
```

**Format conversion** (DER/PKCS12 to PEM):
```bash
openssl x509 -inform der -in cert.der -out cert.pem
openssl pkcs12 -in cert.p12 -out cert.pem -nodes
```

## Validation Status

Certificates are validated at discovery:
- ✅ Valid and accessible
- ❌ Invalid (skipped with error)
- ⚠️ Warning (format issues but usable)

## Security Best Practices

- Store in `credentials/certs/` (gitignored)
- Use PEM format
- Keep certificates updated
- Never commit to Git
