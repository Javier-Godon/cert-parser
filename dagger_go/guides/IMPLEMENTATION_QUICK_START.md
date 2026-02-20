# Implementation Quick Start: Docker + Testcontainers in Dagger

## 5-Minute Integration Guide

### Step 1: Import Testcontainers Module

Update your `dagger.json`:

```json
{
  "name": "railway",
  "sdk": "go",
  "deps": [
    "github.com/vito/daggerverse/testcontainers"
  ]
}
```

Or use CLI:
```bash
dagger mod get github.com/vito/daggerverse/testcontainers
```

### Step 2: Add Test Function (Copy-Paste Ready)

Add this to `main.go`:

```go
// Test runs the Railway framework test suite with Docker support for Testcontainers
func (r *Railway) Test(ctx context.Context) (string, error) {
	testContainer := dag.Container().
		From("maven:3.9-openjdk-25").
		WithMountedDirectory("/app", r.Source).
		With(dag.Testcontainers().Setup). // ← This line handles Docker setup
		WithWorkdir("/app").
		WithExec([]string{
			"mvn",
			"clean",
			"test",
			"-Dorg.slf4j.simpleLogger.defaultLogLevel=info",
		})

	return testContainer.Stdout(ctx)
}
```

### Step 3: Run Tests

```bash
# From dagger_go/ directory
dagger call test

# Or with arguments
dagger call test --source=./
```

---

## Option 2: Advanced Setup (If Testcontainers Module Not Available)

Manually set up Docker binding:

```go
// ManualTestSetup shows how to set up Docker without the module
func (r *Railway) ManualTestSetup(ctx context.Context) (string, error) {
	// Create Docker service
	dockerService := dag.Docker().Daemon().Service()

	testContainer := dag.Container().
		From("maven:3.9-openjdk-25").
		WithMountedDirectory("/app", r.Source).
		WithServiceBinding("docker", dockerService). // ← Bind Docker service
		WithEnvVariable("DOCKER_HOST", "tcp://docker:2375"). // ← Point to service
		WithEnvVariable("TESTCONTAINERS_RYUK_DISABLED", "true"). // ← CI-safe
		WithWorkdir("/app").
		WithExec([]string{"mvn", "clean", "test"})

	return testContainer.Stdout(ctx)
}
```

---

## Multi-Module Testing (For Separate Catalog, Customers, Orders, IAM)

```go
// TestAllModules runs tests for each module with shared Docker
func (r *Railway) TestAllModules(ctx context.Context) (string, error) {
	modules := []string{"catalog", "customers", "orders", "userIam"}
	results := make([]string, 0)

	for _, module := range modules {
		result, err := r.testModule(ctx, module)
		if err != nil {
			return "", fmt.Errorf("module %s failed: %w", module, err)
		}
		results = append(results, fmt.Sprintf("✓ %s: PASSED", module))
	}

	return strings.Join(results, "\n"), nil
}

func (r *Railway) testModule(ctx context.Context, module string) (string, error) {
	testContainer := dag.Container().
		From("maven:3.9-openjdk-25").
		WithMountedDirectory("/app", r.Source).
		With(dag.Testcontainers().Setup).
		WithWorkdir("/app").
		WithExec([]string{
			"mvn",
			"-pl", module,
			"test",
		})

	return testContainer.Stdout(ctx)
}
```

---

## Debugging

### View Docker Daemon Logs
```bash
# Run with verbose output
dagger call test --debug

# Or capture intermediate container
dagger call test -v stdout
```

### Test Without Testcontainers
```go
// Test basic Maven build without containers
func (r *Railway) MavenTest(ctx context.Context) (string, error) {
	testContainer := dag.Container().
		From("maven:3.9-openjdk-25").
		WithMountedDirectory("/app", r.Source).
		WithWorkdir("/app").
		WithExec([]string{"mvn", "clean", "test"})

	return testContainer.Stdout(ctx)
}
```

### Check Environment Variables
```go
// Debug: Show environment variables in container
func (r *Railway) DebugEnv(ctx context.Context) (string, error) {
	debugContainer := dag.Container().
		From("maven:3.9-openjdk-25").
		With(dag.Testcontainers().Setup).
		WithExec([]string{"env"})

	return debugContainer.Stdout(ctx)
}
```

---

## Verification Checklist

- [ ] `dagger mod get` succeeds without errors
- [ ] `dagger call test` runs without timeouts
- [ ] Maven downloads dependencies (may take 1-2 min first run)
- [ ] Tests complete with JUnit reports generated
- [ ] `DOCKER_HOST` is set to `tcp://docker:2375`
- [ ] No "permission denied" errors
- [ ] No "Cannot connect to Docker daemon" errors

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| "Cannot connect to Docker daemon" | Docker not exposed to container | Use `dag.Testcontainers().Setup` |
| Timeout (5+ minutes) | Module download slow | First run is slow; subsequent runs cached |
| "Permission denied" | Running as non-root | Add `WithUser("root")` (not ideal) or check Docker service |
| Ryuk errors | Resource cleanup enabled | Add `WithEnvVariable("TESTCONTAINERS_RYUK_DISABLED", "true")` |

---

## Next Steps

1. ✅ Add to `main.go` and test locally
2. ✅ Verify with `dagger call test`
3. ✅ Add to CI/CD pipeline (GitLab CI, GitHub Actions)
4. ✅ Document in team wiki

For detailed implementation, see: `DAGGER_DOCKER_TESTCONTAINERS_INVESTIGATION.md`
