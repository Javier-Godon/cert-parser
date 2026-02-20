# Quick Reference & Comparisons

Quick reference guides and comparison matrices for fast lookup and decision-making.

## 📚 Contents

### Quick Reference
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - 5-10 minute quick lookup guide for common tasks

### Comparisons
- **[BEFORE_AFTER_COMPARISON.md](BEFORE_AFTER_COMPARISON.md)** - Visual diffs and timeline comparison of pipeline changes

## ⚡ Quick Start Cheat Sheet

### Installation (5 min)
```bash
# 1. Add module dependency (see QUICK_REFERENCE.md)
# 2. Copy functions from ../guides/IMPLEMENTATION_QUICK_START.md
# 3. Run tests
go test ./...
```

### Local Testing
```bash
# With Docker running (full test suite)
./run.sh

# Check Docker status
docker ps

# Verify integration tests run
go test -run TestWithDocker -v
```

### CI/CD Setup
```bash
# GitHub Actions: Docker available by default
# Just export DOCKER_HOST in workflow

# GitLab CI: Use docker-in-docker (dind) image
image: docker:latest
services:
  - docker:dind
```

## 📊 Comparison Matrix

See `BEFORE_AFTER_COMPARISON.md` for:
- Timeline of changes
- Before/After code comparison
- Performance impact (≈30-40 seconds additional for container startup)
- Behavioral differences
- Rollback procedures

## 🔍 Troubleshooting Quick Ref

| Issue | Solution | Reference |
|-------|----------|-----------|
| Docker not found | Check `/var/run/docker.sock` exists | `QUICK_REFERENCE.md` Troubleshooting |
| Permission denied | Add user to docker group: `sudo usermod -aG docker $USER` | `QUICK_REFERENCE.md` |
| Socket permission error | Ensure Docker daemon accessible: `docker ps` | `QUICK_REFERENCE.md` |
| Tests too slow | Expected: +30-40s (container startup) | `QUICK_REFERENCE.md` Performance |
| Container network issues | Verify compose network: `docker network ls` | `QUICK_REFERENCE.md` |

## 🎯 Decision Tree

**Should I use testcontainers?**
- ✅ YES if: Testing integration with external services (DB, APIs, caches)
- ✅ YES if: Need reproducible test environments
- ❌ NO if: Only testing pure business logic
- ❌ NO if: Docker unavailable and can't be installed

**Which solution should I use?**
- See `../integration-testing/TESTCONTAINERS_PIPELINE_INVESTIGATION.md` for full comparison
- Recommended: **Solution 2 + Solution 4** (Docker socket + conditional execution)

## 📈 Performance Impact

| Phase | Time | Impact |
|-------|------|--------|
| Docker detection | <1s | Minimal |
| Container startup | 30-40s | One-time per test run |
| Test execution | Same | No change |
| Graceful skip | <1s | When Docker unavailable |

## 📖 Related Documentation

- Detailed implementation: See `../guides/`
- Integration testing: See `../integration-testing/`
- Deployment: See `../deployment/`
- Architecture: See `../architecture/`
- Full documentation: See `../docs/`

## 🔗 Common Commands

```bash
# Check Docker availability
docker info

# Run full test suite
go test ./...

# Run specific integration tests
go test -run Integration -v

# Check Docker socket
ls -la /var/run/docker.sock

# View container logs
docker logs <container_id>

# Inspect running containers
docker ps -a

# Clean up containers
docker system prune
```

## 📝 Key Files Modified

1. `main.go` - Added Docker detection and conditional test execution
2. `run.sh` - Added Docker availability checking and socket setup
3. `run-corporate.sh` - Added proxy and certificate support
4. Go module - Added testcontainers dependency

See `BEFORE_AFTER_COMPARISON.md` for complete diff view.
