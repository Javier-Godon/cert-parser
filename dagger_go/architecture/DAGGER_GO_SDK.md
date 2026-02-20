# Dagger Go SDK v0.19.7 - Comprehensive Knowledge Base

**Date**: November 20, 2025  
**SDK Version**: v0.19.7  
**Go Minimum**: 1.22+  
**Dagger Engine**: v0.19.7

## Table of Contents

1. [SDK Overview](#sdk-overview)
2. [Core API Patterns](#core-api-patterns)
3. [Best Practices](#best-practices)
4. [Production Patterns](#production-patterns)
5. [Known Limitations](#known-limitations)
6. [Integration with Java Projects](#integration-with-java-projects)

---

## SDK Overview

### What is Dagger Go SDK?

Dagger is a **programmable CI/CD platform** written in Go. The Go SDK provides a type-safe interface to:

- Build Docker containers programmatically
- Orchestrate complex build pipelines
- Cache build artifacts efficiently
- Publish to registries (Docker Hub, GHCR, ECR, etc.)
- Execute arbitrary commands in containers
- Manage secrets securely

### Why Use Go SDK Over Python?

| Aspect | Python | Go |
|--------|--------|-----|
| **Startup Time** | 500-1000ms | ~50ms |
| **Type Safety** | Runtime errors possible | Compile-time checking |
| **Performance** | Interpreted | Compiled binary |
| **Deployment** | Requires Python runtime | Single executable |
| **Cross-Platform** | Platform-specific issues | Universal binary with GOOS/GOARCH |
| **IDE Support** | Limited | Excellent in GoLand/IntelliJ |
| **Learning Curve** | Easy for Python developers | Easy for Go developers |

### Architecture

```
Your Go Program
    ↓ (gRPC)
Dagger Engine (Container)
    ↓ (BuildKit)
Docker Daemon
    ↓
Build Layers, Caches, Images
```

Dagger abstracts away the complexity of coordinating Docker and BuildKit.

---

## Core API Patterns

### 1. Client Connection & Context

```go
package main

import (
    "context"
    "os"
    "dagger.io/dagger"
)

func main() {
    ctx := context.Background()
    
    // Connect to Dagger Engine (auto-starts if needed)
    client, err := dagger.Connect(ctx, 
        dagger.WithLogOutput(os.Stderr),  // Show logs
    )
    if err != nil {
        panic(err)
    }
    defer client.Close()
    
    // Use client...
}
```

**Key Points:**
- `context.Context` tracks operation lifecycle
- `client.Close()` must be called (use defer)
- Dagger Engine runs in a container (managed automatically)

### 2. Container Operations

#### Creating Containers
```go
// From base image
container := client.Container().From("ubuntu:24.04")

// From build stage (multi-stage)
container := client.Container().From("golang:1.22-alpine")
```

#### Executing Commands
```go
// Single command
output, err := container.
    WithExec([]string{"echo", "hello"}).
    Stdout(ctx)

// Chained commands
result := container.
    WithExec([]string{"apt-get", "update"}).
    WithExec([]string{"apt-get", "install", "-y", "git"}).
    WithExec([]string{"git", "--version"})
```

#### Working Directories
```go
container := client.Container().
    From("alpine:latest").
    WithWorkdir("/app").
    WithExec([]string{"pwd"})  // Output: /app
```

#### Environment Variables
```go
container := client.Container().
    From("alpine:latest").
    WithEnvVariable("GO_VERSION", "1.22").
    WithEnvVariable("GOPATH", "/go")
```

### 3. File & Directory Operations

#### Mounting Directories
```go
// From host
source := client.Host().Directory("./src")

container := client.Container().
    From("golang:1.22").
    WithMountedDirectory("/workspace", source).
    WithWorkdir("/workspace").
    WithExec([]string{"go", "build"})
```

#### Copying Files
```go
binary := container.File("/app/binary")

// Write to host
err := binary.Export(ctx, "./binary")
```

#### Directory Exclusions
```go
source := client.Host().Directory(".", dagger.HostDirectoryOpts{
    Exclude: []string{
        "node_modules/**",
        "target/**",
        ".git/**",
    },
})
```

### 4. Volume Management (Caching)

#### Cache Volumes
```go
// Create persistent cache
cache := client.CacheVolume("maven-cache")

// Use in container
container := client.Container().
    From("amazoncorretto:25").
    WithMountedCache("/root/.m2", cache).
    WithExec([]string{"mvn", "clean", "package"})
```

**Benefits:**
- Subsequent builds reuse cached Maven artifacts
- Huge time savings for large projects
- Automatic cleanup when not needed

#### Temporary Volumes
```go
// For file transfers between stages
scratch := client.Container().From("scratch")

// Copy file to scratch volume
file := buildContainer.File("/build/app.jar")
scratch = scratch.WithFile("/app.jar", file)
```

### 5. Secret Management

#### Creating Secrets
```go
// Never log credentials directly
password := client.SetSecret("docker_password", os.Getenv("DOCKER_PASSWORD"))

// Use in registry auth
image := image.WithRegistryAuth("ghcr.io", "username", password)
```

#### In Container
```go
// Mount as file
container := container.WithSecretVariable("GITHUB_TOKEN", secretVar)

// Then in script
container.WithExec([]string{"sh", "-c", "echo $GITHUB_TOKEN"})
```

### 6. Docker Image Building

#### From Dockerfile
```go
dir := client.Host().Directory(".")
image := dir.DockerBuild(dagger.DirectoryDockerBuildOpts{
    Dockerfile: "Dockerfile",
})
```

#### Programmatic Building
```go
image := client.Container().
    From("amazoncorretto:25").
    WithExec([]string{"yum", "install", "-y", "maven"}).
    WithMountedDirectory("/app", source).
    WithWorkdir("/app").
    WithExec([]string{"mvn", "clean", "package"}).
    // Returns Container with final state
    Directory("/app").  // Get directory after build
    DockerBuild()       // Create image from current layer
```

### 7. Publishing to Registries

#### GitHub Container Registry (GHCR)
```go
address, err := image.
    WithRegistryAuth("ghcr.io", username, password).
    Publish(ctx, "ghcr.io/username/repo:tag")
```

#### Docker Hub
```go
address, err := image.
    WithRegistryAuth("docker.io", username, password).
    Publish(ctx, "docker.io/username/repo:tag")
```

#### Amazon ECR
```go
address, err := image.
    WithRegistryAuth(
        "123456789.dkr.ecr.us-east-1.amazonaws.com",
        "AWS",
        awsPassword,  // Use AWS CLI token
    ).
    Publish(ctx, "123456789.dkr.ecr.us-east-1.amazonaws.com/repo:tag")
```

---

## Best Practices

### 1. Error Handling

```go
// ✅ CORRECT: Explicit error handling
if err := buildAndPublish(ctx, client); err != nil {
    fmt.Fprintf(os.Stderr, "ERROR: %v\n", err)
    os.Exit(1)
}

// ❌ WRONG: Ignoring errors
buildAndPublish(ctx, client)  // Silently fails
```

### 2. Resource Cleanup

```go
// ✅ CORRECT: Defer cleanup
client, err := dagger.Connect(ctx)
if err != nil {
    panic(err)
}
defer client.Close()

// ❌ WRONG: No cleanup
client, _ := dagger.Connect(ctx)
// Dagger engine container left running
```

### 3. Context Propagation

```go
// ✅ CORRECT: Use context timeouts
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
defer cancel()

result, err := client.Container()./* ... */.Stdout(ctx)

// ❌ WRONG: No timeout
result, err := client.Container()./* ... */.Stdout(context.Background())
// Pipeline could hang indefinitely
```

### 4. Caching Strategy

```go
// ✅ CORRECT: Multiple cache volumes for different layers
mavencache := client.CacheVolume("maven-cache")      // ~/.m2
npmcache := client.CacheVolume("npm-cache")          // ~/.npm
gradlecache := client.CacheVolume("gradle-cache")    // ~/.gradle

// ✅ CORRECT: Layer caching from Dockerfile
# In Dockerfile, heavy operations first:
RUN apt-get update && apt-get install -y ...  # Cached
COPY . /app                                     # Invalidates on code change
RUN mvn clean package                           # Rebuilds

// ❌ WRONG: No caching
container.WithExec([]string{"mvn", "clean", "package"})
// Every build redownloads dependencies
```

### 5. Logging and Debugging

```go
// ✅ CORRECT: Structured logging
fmt.Printf("📦 Building Java application...\n")
fmt.Printf("   Image: %s\n", imageTag)
fmt.Printf("   Progress: Building...\n")

output, err := container.Stdout(ctx)
fmt.Printf("✅ Build successful\n")

// ❌ WRONG: No progress information
container.Stdout(ctx)  // User doesn't know what's happening
```

### 6. Pipeline Organization

```go
// ✅ CORRECT: Separate concerns
type BuildPipeline struct {
    Source    *dagger.Directory
    BuildCache *dagger.CacheVolume
}

func (p *BuildPipeline) build(ctx context.Context) (*dagger.Container, error) {
    // ...
}

func (p *BuildPipeline) publish(ctx context.Context, img *dagger.Container) (string, error) {
    // ...
}

// ❌ WRONG: All logic in main
func main() {
    // 200 lines of build logic
    // 200 lines of publish logic
}
```

---

## Production Patterns

### Pattern 1: Maven Build with Caching

```go
func buildMavenProject(ctx context.Context, client *dagger.Client) (string, error) {
    // Create cache
    mavenCache := client.CacheVolume("maven-cache")
    
    // Load source
    source := client.Host().Directory(".")
    
    // Build container
    builder := client.Container().
        From("amazoncorretto:25.0.1").
        WithExec([]string{"yum", "install", "-y", "maven"}).
        WithMountedCache("/root/.m2", mavenCache).
        WithMountedDirectory("/app", source).
        WithWorkdir("/app").
        WithExec([]string{
            "mvn", "clean", "package",
            "-DskipTests",
            "-Dmaven.compiler.release=25",
            "-Dmaven.compiler.compilerArgs=--enable-preview",
        })
    
    // Get built JAR
    jar := builder.File("/app/target/app.jar")
    
    // Export to host
    return jar.Export(ctx, "./target/app.jar")
}
```

### Pattern 2: Multi-Stage Docker Build

```go
func multiStageBuild(ctx context.Context, client *dagger.Client) *dagger.Container {
    // Stage 1: Builder
    builder := client.Container().
        From("amazoncorretto:25.0.1").
        WithExec([]string{"yum", "install", "-y", "maven"}).
        WithMountedDirectory("/app", source).
        WithWorkdir("/app").
        WithExec([]string{"mvn", "clean", "package", "-DskipTests"})
    
    // Stage 2: Runtime
    runtime := client.Container().
        From("amazoncorretto:25.0.1").
        WithFile("/app.jar", builder.File("/app/target/app.jar")).
        WithExpose(8080).
        WithEntrypoint([]string{"java", "-jar", "/app.jar"})
    
    return runtime
}
```

### Pattern 3: Parallel Builds (Future)

```go
// Not yet available in v0.19.7, but planned:
// Use goroutines + WaitGroup for true parallelization

func parallelBuilds(ctx context.Context, client *dagger.Client) error {
    var wg sync.WaitGroup
    errors := make(chan error, 2)
    
    // Build Java module
    wg.Add(1)
    go func() {
        defer wg.Done()
        if err := buildJavaModule(ctx, client); err != nil {
            errors <- err
        }
    }()
    
    // Build Docker image (separate)
    wg.Add(1)
    go func() {
        defer wg.Done()
        if err := buildDockerImage(ctx, client); err != nil {
            errors <- err
        }
    }()
    
    wg.Wait()
    // Check for errors...
}
```

---

## Known Limitations

### 1. Windows Path Handling

**Issue:** Backslashes in Windows paths
```go
// ❌ WRONG on Windows
WithMountedDirectory("C:\Users\...", dir)

// ✅ CORRECT: Use filepath
path := filepath.Join("C:", "Users", "...")
WithMountedDirectory(path, dir)
```

### 2. BuildKit Performance

**Issue:** First build slower than subsequent builds
```
First build:  ~45 seconds (BuildKit initialization)
Second build: ~10 seconds (cache hits)
```

### 3. Network Access in Containers

**Issue:** Some registries may not be accessible from container
```go
// ✅ CORRECT: Use explicit registry auth
image.WithRegistryAuth("ghcr.io", user, password)

// May fail if network restricted in build container
```

### 4. Large File Transfers

**Issue:** Transferring large directories can be slow
```go
// ✅ CORRECT: Exclude unnecessary files
client.Host().Directory(".", dagger.HostDirectoryOpts{
    Exclude: []string{"node_modules/**", "target/**"},
})

// ❌ WRONG: Transfer entire directory
client.Host().Directory(".")  // Could be GBs
```

---

## Integration with Java Projects

### Maven + Dagger Go Pattern

```go
// Your dagger_go/main.go
func buildJavaProject(ctx context.Context, client *dagger.Client) error {
    source := client.Host().Directory(".")
    mavenCache := client.CacheVolume("maven-cache")
    
    jar := client.Container().
        From("amazoncorretto:25.0.1").
        WithExec([]string{"yum", "install", "-y", "maven"}).
        WithMountedCache("/root/.m2", mavenCache).
        WithMountedDirectory("/app", source).
        WithWorkdir("/app").
        WithExec([]string{"mvn", "clean", "package", "-DskipTests"}).
        File("/app/target/app.jar")
    
    // Export built JAR
    return jar.Export(ctx, "./target/app.jar")
}
```

### Spring Boot Application Deployment

```go
func deploySpringBoot(ctx context.Context, client *dagger.Client, imageTag string) error {
    // Build JAR
    jar := buildJavaProject(ctx, client)
    
    // Create runtime image
    runtime := client.Container().
        From("amazoncorretto:25.0.1").
        WithFile("/app.jar", jar).
        WithEnvVariable("JAVA_OPTS", "--enable-preview").
        WithExpose(8080, dagger.ContainerExposeOpts{
            Description: "Spring Boot application",
        }).
        WithEntrypoint([]string{
            "java", "$JAVA_OPTS", "-jar", "/app.jar",
        })
    
    // Publish
    password := client.SetSecret("ghcr_token", os.Getenv("GITHUB_TOKEN"))
    _, err := runtime.
        WithRegistryAuth("ghcr.io", username, password).
        Publish(ctx, imageTag)
    
    return err
}
```

### Kubernetes Integration

```go
func deployToKubernetes(ctx context.Context, image string) error {
    // Use kubectl to deploy the built image
    return exec.CommandContext(ctx,
        "kubectl", "set", "image",
        "deployment/railway",
        fmt.Sprintf("railway=%s", image),
    ).Run()
}
```

---

## SDK Versioning

| Version | Release Date | Status | Notes |
|---------|--------------|--------|-------|
| v0.19.7 | Nov 20, 2025 | ✅ Current | Latest stable |
| v0.19.6 | Nov 7, 2025 | ✅ Stable | Older release |
| v0.18.x | Earlier | ✅ Maintained | Legacy support |

### Upgrading Go SDK

```bash
# Check current version
go list -m dagger.io/dagger

# Update to latest
go get -u dagger.io/dagger

# Update to specific version
go get dagger.io/dagger@v0.19.7
```

---

## Performance Optimization Tips

1. **Use cache volumes** for package managers
2. **Layer operations smartly** (expensive operations first)
3. **Exclude large directories** from mounts
4. **Use appropriate base images** (alpine < ubuntu < debian)
5. **Multi-stage builds** to reduce final image size

---

## Debugging

```go
// Enable verbose logging
client, err := dagger.Connect(ctx,
    dagger.WithLogOutput(os.Stderr),
)

// Use WithExec with explicit commands
output, err := container.
    WithExec([]string{"set", "-x"}).  // bash debug mode
    Stdout(ctx)

// Check intermediate results
fmt.Printf("DEBUG: %v\n", someContainer)
```

---

## Resources

- 📖 [Dagger Go Docs](https://docs.dagger.io/sdk/go)
- 🔗 [Go Package Reference](https://pkg.go.dev/dagger.io/dagger@v0.19.7)
- 🐙 [GitHub Repository](https://github.com/dagger/dagger)
- 💬 [Discord Community](https://discord.gg/dagger-io)

---

**Last Updated**: November 20, 2025  
**SDK Version**: v0.19.7  
**Go Version**: 1.22+
