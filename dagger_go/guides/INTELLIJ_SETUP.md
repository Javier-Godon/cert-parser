# IntelliJ IDEA Configuration for cert-parser (Python + Go)

This guide explains how to configure IntelliJ IDEA to work with both the Python
application (`src/cert_parser/`) and the Go Dagger pipeline (`dagger_go/`) in the
same workspace.

## Option 1: Multi-Root Workspace (Recommended)

### Step 1: Open the Python Project
```
IntelliJ IDEA → Open → /path/to/cert-parser
```
IntelliJ will detect `pyproject.toml` and suggest configuring a Python SDK.

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
├── src/cert_parser/   (Python — hexagonal architecture)
├── python_framework/  (local railway-rop package)
├── tests/             (pytest unit/integration/acceptance)
├── dagger_go/         (Go — Dagger CI/CD pipeline)
└── .idea/             (Workspace config)
```

## Option 2: Open Only the Go Module

If you only want to work on the Dagger pipeline:

```bash
open -a "IntelliJ IDEA" dagger_go/

# Or via command line
idea dagger_go
```

## Option 3: Separate Windows

```
Window → New Window → Open Directory...
```

Two IntelliJ windows:
- Window 1: `cert-parser` (Python application)
- Window 2: `dagger_go` (Go Dagger pipeline)

---

## Run Configurations

### Running the Dagger Go Pipeline from IDE

1. **Create Run Configuration**
   ```
   Run → Edit Configurations → [+] → Go
   ```

2. **Configure Parameters**
   ```
   Name: cert-parser Dagger Pipeline
   Kind: Directory
   Directory: dagger_go
   Program arguments: (leave empty)
   Environment variables:
     CR_PAT=your-token
     USERNAME=your-username
     GIT_HOST=github.com
     REGISTRY=ghcr.io
   ```

3. **Run**
   ```
   Run → Run 'cert-parser Dagger Pipeline'
   ```

### Debugging Go Code

```
Run → Debug 'cert-parser Dagger Pipeline'
```

Set breakpoints by clicking line numbers:
```go
// Click to set breakpoint
pipeline := &Pipeline{
    RepoName: repoName,  // ← Breakpoint here
    GitHost:  gitHost,
    Registry: registry,
}
```

---

## IDE Features Setup

### Code Formatting
- **Settings → Go → Code Style → Enable "Run gofmt on Save"**
- **Settings → Go → Go Modules → Enable Go Modules integration**
- **Settings → Python → Enable ruff** (via File Watchers plugin or external tool)

### Linting (golangci-lint)
```bash
# Install golangci-lint
brew install golangci-lint

# Settings → Go → Linter → Choose: golangci-lint
```

### Testing Go
```
Right-click main_test.go → Run 'Go test cert-parser-dagger-go'
```

### Testing Python (pytest)
```
Right-click tests/ → Run pytest
```

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| **Run** | Ctrl+Shift+R |
| **Debug** | Ctrl+D |
| **Format** | Ctrl+Alt+L |
| **Go to Definition** | Ctrl+B |
| **Rename** | Shift+F6 |
| **Find Usages** | Alt+F7 |

---

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
# Go setup
export GOPATH=$HOME/go
export GOROOT=$(go env GOROOT)

# Registry & Git host (defaults to GitHub + GHCR — override as needed)
export GIT_HOST="github.com"
export REGISTRY="ghcr.io"
export GIT_AUTH_USERNAME="x-access-token"

# Credentials (set your own — never commit these)
export CR_PAT="<your-token>"
export USERNAME="<your-username>"
```

Then IntelliJ automatically inherits these when opened in the project:

```bash
cd cert-parser
direnv allow
idea .
```

---

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

### IDE Freezing with Large Go Modules
```
Settings → Go → Build Tags & OS
→ Disable indexing of large dependencies
```

---

## Performance Optimization

```
Help → Edit Custom VM Options
-Xmx2g  (Increase if you have RAM)
-XX:+UseG1GC  (Better GC for mixed workload)
```

---

## Next Steps

1. ✅ Open project in IntelliJ
2. ✅ Configure Python and Go SDKs
3. ✅ Set `CR_PAT` and `USERNAME` in run configuration or `.envrc`
4. ✅ Run Go tests: `cd dagger_go && go test -v`
5. ✅ Run Python tests: `pytest -v`
6. ✅ Create run configurations for both pipelines
