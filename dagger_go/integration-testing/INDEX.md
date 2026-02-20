# Integration Testing with Testcontainers

Comprehensive documentation for Docker-integrated testing with Testcontainers in Dagger pipelines.

## 📚 Contents

### Core Investigation
- **[README_TESTCONTAINERS_INVESTIGATION.md](README_TESTCONTAINERS_INVESTIGATION.md)** - Index and navigation for testcontainers documentation
- **[TESTCONTAINERS_PIPELINE_INVESTIGATION.md](TESTCONTAINERS_PIPELINE_INVESTIGATION.md)** - 5 complete solutions with pros/cons analysis

### Implementation Details
- **[TESTCONTAINERS_IMPLEMENTATION_GUIDE.md](TESTCONTAINERS_IMPLEMENTATION_GUIDE.md)** - Production-ready implementation guide with:
  - Docker socket detection and mounting
  - Test environment setup
  - CI/CD integration
  - Troubleshooting & FAQ

## 🎯 Solution Overview

### Solution 1: Docker Socket Binding (⭐ RECOMMENDED)
- Direct Docker socket mounting
- Best for: Local development and CI with Docker access
- Pros: Simple, direct, low overhead
- Cons: Requires Docker on host

### Solution 2: Conditional Execution (⭐ RECOMMENDED)
- Skip tests when Docker unavailable
- Best for: Mixed environments
- Pros: Graceful degradation, works everywhere
- Cons: Reduced test coverage when Docker unavailable

### Solution 3: Container-Based Execution
- Run everything in containers
- Best for: Complete isolation
- Pros: Reproducible, fully isolated
- Cons: Complex setup, overhead

### Solution 4: Hybrid Approach
- Combine Solutions 1 & 2
- Best for: Production deployments
- Pros: Optimal for all scenarios
- Cons: Requires configuration

### Solution 5: Kubernetes (if available)
- Use Kubernetes for container management
- Best for: Cluster environments
- Pros: Enterprise grade, scalable
- Cons: Overkill for CI, requires K8s

## ✅ Recommended: Solution 2 + Solution 4

**Docker socket binding** (Solution 1) with **conditional execution** (Solution 2) provides:
- ✅ Works in all environments
- ✅ Graceful degradation
- ✅ Production-ready error handling
- ✅ CI/CD compatible
- ✅ Zero breaking changes

## 🚀 Quick Start

See `../guides/TESTCONTAINERS_IMPLEMENTATION_GUIDE.md` for step-by-step implementation.

## 📊 Key Features

- **Auto-detection**: Automatically detects Docker availability
- **Error handling**: Graceful fallback when Docker unavailable
- **Logging**: Enhanced logging without sensitive data
- **CI/CD ready**: Works with GitHub Actions, GitLab CI, Jenkins
- **Cross-platform**: Supports Linux, macOS, Windows with Docker Desktop

## 🔍 Testing Strategies

1. **Local with Docker**: Full test suite (unit + integration)
2. **Local without Docker**: Unit tests only (graceful skip)
3. **CI with Docker**: Full test suite in pipeline
4. **CI without Docker**: Unit tests with warning
5. **Debugging**: Verbose logging and container inspection

## 📖 Related Documentation

- Implementation guides: See `../guides/`
- Deployment & CI/CD: See `../deployment/`
- Architecture overview: See `../architecture/`
- Quick reference: See `../reference/QUICK_REFERENCE.md`
