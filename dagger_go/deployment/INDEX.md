# Deployment & CI/CD Pipelines

Deployment guides, CI/CD integration, and corporate environment support.

## 📚 Contents

### Pipeline Documentation
- **[CORPORATE_PIPELINE.md](CORPORATE_PIPELINE.md)** - Corporate environment setup with MITM proxy and custom CA support
- **[CORPORATE_QUICK_REFERENCE.md](CORPORATE_QUICK_REFERENCE.md)** - Quick reference for corporate pipeline operations

## 🎯 Pipeline Features

### Corporate Environment Support
- MITM proxy configuration
- Custom CA certificate handling
- Certificate chain validation
- Proxy authentication (if required)

### CI/CD Integration
- GitHub Actions integration
- GitLab CI integration
- Jenkins pipeline support
- Docker daemon availability detection

### Deployment Strategies

1. **Standard Deployment**
   - Use `run.sh` for default pipeline
   - Docker detection and testcontainers support
   - Works in most environments

2. **Corporate Deployment**
   - Use `run-corporate.sh` for corporate setup
   - MITM proxy support
   - Custom CA certificate mounting
   - Enhanced logging and diagnostics

## 🚀 Quick Start

### Standard Pipeline
```bash
cd dagger_go
./run.sh
```

### Corporate Pipeline
```bash
# 1. Set up certificates in credentials/certs/
# 2. Configure proxy in credentials/.env (optional)
cd dagger_go
./run-corporate.sh
```

## 📋 Configuration

### Corporate Proxy Setup
```bash
# credentials/.env
PROXY_HOST=proxy.company.com
PROXY_PORT=3128
PROXY_USER=username
PROXY_PASSWORD=password

# CA Certificates
# Place .pem files in credentials/certs/
# - company-root-ca.pem
# - company-intermediate-ca.pem
# - proxy-mitm-ca.pem
```

## 🔍 Diagnostics

### Certificate Diagnostics
```bash
./run-corporate.sh --diagnostics
```

### Verbose Output
```bash
./run-corporate.sh --verbose
```

### Docker Availability Check
```bash
docker ps
docker info | grep "Docker Root Dir"
```

## 📊 Environment Detection

The pipeline automatically detects:
- ✅ Docker daemon availability
- ✅ Docker socket location (platform-specific)
- ✅ Proxy settings from environment
- ✅ CA certificates in `credentials/certs/`
- ✅ Current execution context (CI vs local)

## 🛠️ Troubleshooting

### Docker Socket Not Found
- Linux: Ensure `/var/run/docker.sock` exists
- macOS: Use `$(docker context inspect -f '{{.Endpoints.docker.Host}}')` to find socket
- Windows: Ensure Docker Desktop is running

### Certificate Chain Validation Failed
- Run with `--diagnostics` flag to see full chain
- Verify `.pem` files are valid certificates
- Check file permissions in `credentials/certs/`

### Proxy Connection Issues
- Verify proxy host, port, and credentials
- Test: `curl -x http://user:pass@proxy:port https://docker.io`
- Check firewall/network policies

## 📖 Related Documentation

- Integration testing: See `../integration-testing/`
- Implementation guides: See `../guides/`
- Architecture: See `../architecture/`
- Quick reference: See `../reference/`
