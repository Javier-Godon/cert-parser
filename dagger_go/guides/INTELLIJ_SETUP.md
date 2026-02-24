# IntelliJ IDEA Configuration for Mixed Java/Go Project

This guide explains how to configure IntelliJ IDEA to work with both Java (Spring Boot) and Go (Dagger) modules in the same workspace.

## Option 1: Multi-Root Workspace (Recommended)

### Step 1: Open Java Project First
```
IntelliJ IDEA → Open → /path/to/cert-parser
```

### Step 2: Attach Go Module
```
File → Project Structure → Modules → [+] 
  → Import Module (not New Module)
  → Select: dagger_go directory
  → Select: Go as module type
```

### Step 3: Configure Go SDK
```
File → Project Structure → SDKs → [+] Add SDK
  → Choose Go SDK
  → Browse to your Go installation (/usr/local/go or brew location)
```

Result:
```
cert-parser (Project Root)
├── python_framework (Java Module)
├── dagger_go (Go Module)
└── .idea/ (Workspace config)
```

## Option 2: Open Only Go Module

If you only want to work on the Go pipeline:

```bash
open -a "IntelliJ IDEA" dagger_go/

# Or via command line
idea dagger_go
```

## Option 3: Folder-Based Workspace

Create a workspace file for quick switching:

### In IntelliJ
```
Window → New Window → Open Directory...
```

This allows having multiple IntelliJ windows:
- Window 1: `cert-parser` (Java/Spring Boot)
- Window 2: `dagger_go` (Go/Dagger)

## Run Configurations

### Running the Dagger Go Pipeline from IDE

1. **Create Run Configuration**
   ```
   Run → Edit Configurations → [+] → Go
   ```

2. **Configure Parameters**
   ```
   Name: Railway Dagger Pipeline
   Kind: Directory
   Directory: dagger_go
   Program arguments: (leave empty)
   Environment variables:
     CR_PAT=your-token
     USERNAME=your-username
   ```

3. **Run**
   ```
   Run → Run 'Railway Dagger Pipeline'
   ```

### Debugging Go Code

```
Run → Debug 'Railway Dagger Pipeline'
```

Set breakpoints by clicking line numbers:
```go
// Line 45: click to set breakpoint
pipeline := &RailwayPipeline{
    RepoName: repoName,  // ← Breakpoint here
}
```

## IDE Features Setup

### Code Formatting
- **Settings → Go → Code Style → Enable "Run gofmt on Save"**
- **Settings → Go → Go Modules → Enable Go Modules integration**

### Linting (golangci-lint)
```bash
# Install golangci-lint
brew install golangci-lint

# Settings → Go → Linter
# Choose: golangci-lint
```

### Testing
```
View → Tool Windows → Run
```

Run tests directly:
```
Right-click main_test.go → Run 'TestProjectRootDiscovery'
```

## Module Dependencies

### Java Module Depends on Docker Output (Optional)

For advanced setup, you could configure Maven to:
1. Call the Go Dagger pipeline before building
2. Use generated Docker image as deployment target

This requires:
```xml
<!-- In python_framework/pom.xml -->
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>exec</goal></goals>
            <configuration>
                <executable>../dagger_go/run.sh</executable>
            </configuration>
        </execution>
    </executions>
</plugin>
```

## Keyboard Shortcuts

| Action | Java | Go |
|--------|------|-----|
| **Run** | Ctrl+Shift+R | Ctrl+Shift+R (same) |
| **Debug** | Ctrl+D | Ctrl+D (same) |
| **Format** | Ctrl+Alt+L | Ctrl+Alt+L (same) |
| **Go to Definition** | Ctrl+B | Ctrl+B (same) |
| **Rename** | Shift+F6 | Shift+F6 (same) |
| **Find Usages** | Alt+F7 | Alt+F7 (same) |

## Version Control Integration

Both Java and Go are properly integrated with Git:

```
Git window shows:
├── dagger_go/
│   ├── go.mod (modified)
│   ├── go.sum (modified)
│   └── main.go (modified)
├── python_framework/
│   └── pom.xml (modified)
```

Commit/push works across both modules seamlessly.

## File Watching

IntelliJ automatically watches both:
- **Java**: `*.java`, `pom.xml`, `*.xml`
- **Go**: `*.go`, `go.mod`, `go.sum`

Changes trigger appropriate rebuilds/recompilation.

## Troubleshooting

### Go Module Not Recognized
```
File → Project Structure → Modules
→ Ensure "dagger_go" is listed
→ Ensure Go SDK is configured in Project Settings
```

### Can't Run Go Code
```
File → Project Structure → SDKs → [+]
→ Add Go SDK pointing to: $(go env GOROOT)
```

### Maven Still Trying to Build dagger_go
```
File → Project Structure → Modules
→ Select dagger_go
→ Mark folder as: Excluded
```

### IDE Freezing with Large Go Modules
```
Settings → Go → Build Tags & OS
→ Disable indexing of large dependencies
```

## Environment Setup Script

Create `.envrc` for automatic environment loading (requires `direnv`):

```bash
# Install direnv
brew install direnv

# Add to ~/.zshrc or ~/.bash_profile
eval "$(direnv hook zsh)"
```

Then create `cert-parser/.envrc`:

```bash
# Java setup
export JAVA_HOME=$(/usr/libexec/java_home -v 25)
export MAVEN_HOME=$(brew --cellar maven)/$(brew list maven | head -1)

# Go setup  
export GOPATH=$HOME/go
export GOROOT=$(go env GOROOT)

# GitHub credentials (set your own)
export CR_PAT="<your-token>"
export USERNAME="<your-username>"
```

Then IntelliJ automatically inherits these when opened in the project:

```bash
cd cert-parser
direnv allow
idea .
```

## Performance Optimization

For smoother IDE performance with both Java and Go:

### Settings
```
File → Project Structure → Project
→ Compiler: Use out-of-process build
→ Settings → Build, Execution, Deployment
→ Build Tools → Maven → Compiler: Use out-of-process build
```

### Memory Allocation
```
Help → Edit Custom VM Options
-Xmx2g  (Increase if you have RAM)
-XX:+UseG1GC  (Better GC for mixed workload)
```

### Indexing
```
Settings → IDE → Indexing
→ Disable indexing of: Go vendor/, node_modules/
```

## Next Steps

1. ✅ Open project in IntelliJ
2. ✅ Configure both Java and Go SDKs
3. ✅ Run Java build: `mvn clean compile`
4. ✅ Run Go pipeline: `./test.sh`
5. ✅ Create run configurations
6. ✅ Test debugging in both modules

You now have a fully integrated Java/Go development environment in IntelliJ IDEA!
