# Architecture & Design

Technical architecture, design patterns, and system discovery mechanisms.

## 📚 Contents

### Core Architecture
- **[DAGGER_GO_SDK.md](DAGGER_GO_SDK.md)** - Dagger Go SDK documentation and patterns
- **[AUTO_DISCOVERY_EXPLAINED.md](AUTO_DISCOVERY_EXPLAINED.md)** - Automatic discovery mechanism for Docker and certificates

### Certificate & Discovery
- **[CERTIFICATE_DISCOVERY.md](CERTIFICATE_DISCOVERY.md)** - Certificate discovery and validation process

## 🎯 Architecture Overview

### Docker Socket Detection
- Automatic detection of Docker daemon availability
- Platform-specific socket paths:
  - Linux: `/var/run/docker.sock`
  - macOS: `${HOME}/.docker/run/docker.sock` or Docker Desktop socket
  - Windows: Docker Desktop integration

### Certificate Discovery
- Automated CA certificate discovery in `credentials/certs/`
- Support for custom MITM proxy certificates
- Certificate chain validation and verification

### Design Patterns
- Handler → Aggregator → Stages pattern
- Result<T> monads for error handling
- Immutable aggregators with @With pattern
- Pure functions for business logic

## 🔧 Key Components

### Dagger Container Management
- **setupBuilder()**: Initialize container builder with environment setup
- **checkDockerAvailability()**: Detect Docker daemon and socket
- **runTests()**: Execute test suite with conditional logic

### Discovery Mechanisms
- **Auto-discovery**: Scan and register available components
- **Certificate discovery**: Automatic CA certificate detection
- **Socket discovery**: Find Docker socket at runtime

## 📊 System Architecture

```
Dagger Pipeline
├── Docker Availability Check
│   ├── Linux: /var/run/docker.sock
│   ├── macOS: ~/.docker/run/docker.sock
│   └── Windows: Docker Desktop socket
├── Certificate Discovery
│   ├── Scan credentials/certs/
│   ├── Validate certificate chain
│   └── Mount into container
└── Conditional Test Execution
    ├── With Docker: Unit + Integration
    └── Without Docker: Unit only
```

## 🏗️ Design Principles

1. **Graceful Degradation**: Works everywhere, full features when possible
2. **Auto-Discovery**: Minimal configuration required
3. **Security First**: Never expose credentials or tokens in logs
4. **Immutability**: Use @With pattern for state management
5. **Error Propagation**: Use Result<T> instead of exceptions

## 📖 Related Documentation

- Implementation: See `../guides/`
- Integration testing: See `../integration-testing/`
- Deployment: See `../deployment/`
- Quick reference: See `../reference/`
- Complete investigation: See `../docs/`
