# Quick Reference: Testcontainers in Dagger Pipeline

## 🎯 The Problem

```
❌ Current State:
   Dagger Pipeline → Run Unit Tests → Build Artifact → Publish
                      (no Docker access for testcontainers)

✅ Desired State:
   Dagger Pipeline → Unit Tests + Integration Tests → Build Artifact → Publish
                      (with Docker access for testcontainers)
```

---

## 🔧 Five Solutions Evaluated

| Solution | Pros | Cons | Best For |
|----------|------|------|----------|
| **1. Docker-in-Docker (DinD)** | Full Docker capabilities | Complex, slow, security concerns | Kubernetes only |
| **2. Docker Socket Binding** ⭐ | Simple, fast, no overhead | Needs Docker on host | Most cases |
| **3. Separate Test Stage** | Clean separation | More complex pipeline | Large projects |
| **4. Conditional Execution** ⭐ | Works everywhere | Reduced coverage sometimes | Universal pipelines |
| **5. Graceful Fallback** | Best effort | Hides problems | Dev environments |

**Recommended: Combine 2 + 4 (Docker Socket + Conditional Execution)**

---

## 📋 Implementation Checklist

### Phase 1: Update Code (15 minutes)

```bash
# 1. Backup original
cp dagger_go/main.go dagger_go/main.go.backup

# 2. Update main.go with:
#    - setupBuilder() method
#    - checkDockerAvailability() method
#    - runTests() method
#    - HasDocker field in struct

# 3. Update run.sh:
#    - Add Docker detection
#    - Export DOCKER_HOST
#    - Better error messages

# 4. Verify compilation
cd dagger_go
go mod tidy
go build -o railway-dagger-go main.go
```

### Phase 2: Test Locally (10 minutes)

```bash
# 1. With Docker running
docker ps  # Verify access
cd dagger_go
go run main.go
# ✅ Should run full test suite (unit + integration)

# 2. Verify integration tests run
go run main.go 2>&1 | grep -E "integration|testcontainers|PostgreSQL"

# 3. Check test output includes both phases
go run main.go 2>&1 | tail -30
```

### Phase 3: CI/CD Validation (5 minutes)

```bash
# 1. Push code
git add dagger_go/main.go dagger_go/run.sh
git commit -m "feat: Add testcontainers support to Dagger pipeline"
git push origin main

# 2. Monitor GitHub Actions
# Watch workflow → verify Docker detection → integration tests run

# 3. Verify image published
ghcr.io/YOUR_USERNAME/railway-framework:latest
```

### Phase 4: Optional - Test Annotations (5 minutes)

```java
// Add @Tag("integration") to:
// - CatalogRepositoryImplIntegrationTest.java
// - Any test using @Testcontainers or PostgreSQLContainer

// Add @Tag("unit") to:
// - UpdateOrderStagesTest.java
// - CreateCategoryStagesTest.java
// - Any pure function tests
```

```bash
# Test annotation-based filtering
mvn test -Dgroups=integration          # Integration only
mvn test -DexcludedGroups=integration  # Unit only
```

---

## 🏃 Quick Start

### Option A: Just Mount Socket (5 minutes)

Copy this into your `setupBuilder` method:

```go
// Try to mount Docker socket for testcontainers
if dockerSocket := os.Getenv("DOCKER_HOST"); dockerSocket != "" {
    builder = builder.WithUnixSocket(dockerSocket, client.UnixSocket(dockerSocket))
} else {
    builder = builder.WithUnixSocket("/var/run/docker.sock", client.UnixSocket("/var/run/docker.sock"))
}
```

Then ensure Docker client is installed:

```go
builder = builder.WithExec([]string{"yum", "install", "-y", "docker"})
```

### Option B: Full Implementation (20 minutes)

Use the complete code from `TESTCONTAINERS_IMPLEMENTATION_GUIDE.md`

---

## 🐛 Troubleshooting

### "Docker socket not found"
```bash
# Check if Docker is running
docker ps

# Check socket exists
ls -la /var/run/docker.sock

# Ensure permissions
sudo chmod 666 /var/run/docker.sock  # or add user to docker group
```

### "Testcontainers cannot connect"
```bash
# Check Docker daemon accessibility
docker ps

# Check testcontainers logs
mvn test -Dgroups=integration -X | grep -i "testcontainers"

# Verify container network
docker network ls
```

### "Pipeline slower with integration tests"
```bash
# Expected: +30-40 seconds (container startup)
# If >60s slower, check:
mvn test -Dgroups=integration -q  # Time this locally
```

### "Works locally but fails in CI"
```bash
# Check: GitHub Actions has Docker by default
# Verify: DOCKER_HOST variable set correctly
# Try: Export explicitly in workflow
```

---

## 📊 Expected Results

### Build Output - With Docker Available
```
🚀 Starting railway_oriented_java CI/CD Pipeline (Go SDK v0.19.7)...
   Repository: https://github.com/USERNAME/railway_oriented_java.git (branch: main)
🔖 Getting Git repository...
   Commit: a1b2c3d4e5f6
🔨 Setting up build environment...
   📌 Checking for default Docker socket: /var/run/docker.sock
🐳 Checking Docker availability for integration tests...
   ✅ Docker available - will run full test suite (unit + integration)
🧪 Running tests...
   → Running full test suite (unit + integration)
   ✅ Tests passed successfully
📦 Building Maven artifact...
   ✅ Build completed successfully
🐳 Building Docker image...
📤 Publishing to: ghcr.io/USERNAME/railway-framework:v1.0.0-a1b2c3d-20251123-1234
✅ Images published:
   📦 Versioned: ghcr.io/USERNAME/railway-framework:v1.0.0-a1b2c3d-20251123-1234
   📦 Latest: ghcr.io/USERNAME/railway-framework:latest
🎉 Pipeline completed successfully!
```

### Build Output - Without Docker Available
```
🚀 Starting railway_oriented_java CI/CD Pipeline...
...
🐳 Checking Docker availability for integration tests...
   ⚠️  Docker NOT available - will run unit tests only
🧪 Running tests...
   → Running unit tests only (integration tests skipped)
   ✅ Tests passed successfully
📦 Building Maven artifact...
...
🎉 Pipeline completed successfully!
```

---

## 🔑 Key Takeaways

1. **Docker Socket Mounting** is the simplest solution
2. **Conditional Testing** ensures universal compatibility
3. **Graceful Degradation** = pipeline always succeeds (limited scope if needed)
4. **Test Categorization** (optional) enables fine-grained control
5. **Integration tests catch real bugs** that unit tests miss

---

## 📚 Full Documentation Files

1. **TESTCONTAINERS_PIPELINE_INVESTIGATION.md** (70+ kb)
   - Detailed analysis of all 5 solutions
   - Environment configuration examples
   - CI/CD platform specific guidance

2. **TESTCONTAINERS_IMPLEMENTATION_GUIDE.md** (40+ kb)
   - Complete code for main.go with all methods
   - run.sh script with Docker detection
   - Troubleshooting & testing procedures

3. **BEFORE_AFTER_COMPARISON.md** (30+ kb)
   - Visual pipeline comparison
   - Code diffs showing exact changes
   - Success metrics & rollback strategy

---

## 🎬 Decision Tree

```
Does your host have Docker?
  │
  ├─ YES (Local dev, GitHub Actions, GitLab CI)
  │  └─→ Use Solution 2 (Docker Socket Binding)
  │      └─→ Mount /var/run/docker.sock in Dagger
  │      └─→ Full test suite runs automatically
  │
  └─ NO (Kubernetes-only, restricted environments)
     └─→ Use Solution 5 (Graceful Fallback)
         └─→ Run unit tests only
         └─→ Integration tests skipped with warning
```

---

## 💾 Files to Modify

```
dagger_go/
├── main.go                                    (UPDATE)
│   └── Add: setupBuilder(), checkDockerAvailability(), runTests()
│   └── Update: run() method with new stages
│   └── Add: HasDocker field to RailwayPipeline struct
│
└── run.sh                                     (UPDATE)
    └── Add Docker detection
    └── Export DOCKER_HOST variable
    └── Better error messaging

Optional:
railway_framework/
└── src/test/java/**/*IntegrationTest.java    (ADD @Tag("integration"))
```

---

## ⏱️ Time Estimates

| Task | Time | Difficulty |
|------|------|-----------|
| Read investigation | 10 min | Easy |
| Understand solutions | 15 min | Medium |
| Implement code | 20 min | Medium |
| Test locally | 15 min | Easy |
| Deploy to CI/CD | 10 min | Easy |
| Add test annotations | 5 min | Easy |
| **Total** | **~75 min** | **Medium** |

---

## ✅ Success Criteria

- [ ] Integration tests discovered and categorized
- [ ] Docker socket detected automatically
- [ ] Full test suite runs locally with Docker
- [ ] Unit tests only run when Docker unavailable
- [ ] GitHub Actions pipeline succeeds with integration tests
- [ ] Build time increased by <45 seconds
- [ ] No code changes needed in application code
- [ ] Documentation updated with new pipeline

---

## 📞 Support Decision Points

**"Should I implement this now?"**
- If integration tests fail silently → ✅ YES
- If you need database verification → ✅ YES
- If pipeline is already working → ✓ LOW PRIORITY

**"Which solution should I pick?"**
- For 95% of cases → **Solution 2+4** (Docker Socket + Conditional)
- For Kubernetes only → **Solution 1** (DinD)
- For maximum compatibility → **Solution 4** (Conditional only)

**"What if it breaks?"**
- Rollback: `git checkout HEAD~1 -- dagger_go/main.go`
- Or: `export DOCKER_HOST="" && go run main.go` (disable Docker socket)

