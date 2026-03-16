# Visual Studio Code Setup for Dagger Go Pipeline

This guide explains how to configure **Visual Studio Code (VSC)** to develop and run the cert-parser Python Dagger Go CI/CD pipeline.

**Why VSC for Go?**
- Go is first-class citizen in VSC
- Excellent extension ecosystem
- Lightweight and fast
- Free and open-source
- Good for both Go (pipeline) and Python (application)

---

## ⚡ Quick Start: 3 Minutes to Build & Run

### Prerequisites

- **Visual Studio Code** installed
- **Go 1.22+** installed
- **Docker** running
- **credentials/.env** configured

### Step 1: Open Workspace (30 seconds)

```bash
cd /home/javier/javier/workspaces/cert-parser
code .
```

### Step 2: Run Tests (1 minute)

```
Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go
```

Watch terminal: ✅ Tests pass, dependencies download, binary compiles

### Step 3: Build & Deploy (1 minute)

```
Ctrl+Shift+P → Tasks: Run Task → Run Dagger Pipeline
```

Watch terminal:
- 🐍 pip installs Python dependencies
- 🧪 pytest runs unit/integration/acceptance tests
- 🔍 ruff lint + mypy type-check
- 🐳 Docker builds container image
- 📤 Image pushed to container registry
- ✅ Pipeline complete

**That's it! Your Dagger Go CI/CD pipeline is running.**

---

## Prerequisites

- **Visual Studio Code** (free version)
- **Go 1.22+**
- **Docker** (running)
- **credentials/.env** with CR_PAT and USERNAME

❌ **Dagger CLI NOT required** - Uses Dagger Go SDK v0.19.7 in pipeline

## Installation & Setup

### Step 1: Install Visual Studio Code Extensions

Open VSC and install these extensions:

1. **Go** (official)
   - Publisher: Go Team at Google
   - ID: `golang.go`
   - Rating: ★★★★★ (1M+ downloads)
   - Features: Debugging, testing, intellisense

2. **Docker** (optional but recommended)
   - Publisher: Microsoft
   - ID: `ms-azuretools.vscode-docker`
   - Features: Dockerfile syntax highlighting, image management

3. **GitHub Copilot** (optional)
   - Publisher: GitHub
   - ID: `github.copilot`
   - Features: AI-assisted coding

4. **Error Lens** (recommended)
   - Publisher: Alexander
   - ID: `usernamehw.errorlens`
   - Features: Inline error/warning display

### Installation Steps

```
VSC → Extensions → Search "Go" → Click "Go" → Install
VSC → Extensions → Search "Docker" → Click "Docker" → Install
```

Or use command line:

```bash
code --install-extension golang.go
code --install-extension ms-azuretools.vscode-docker
```

### Step 2: Configure Go Environment

Open VSC and go to:

```
File → Preferences → Settings (Cmd+,)
```

Search for "Go" and configure:

```json
{
  "[go]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": true,
      "source.organizeImports": true
    }
  },
  "go.lintOnSave": "package",
  "go.lintTool": "golangci-lint",
  "go.useLanguageServer": true,
  "go.languageServerFlags": ["-rpc.trace"],
  "go.coverOnSingleTestFile": true,
  "go.testEnvVars": {
    "GO111MODULE": "on"
  }
}
```

### Step 3: Install Go Tools

VSC will prompt to install Go tools. Accept all prompts:

- `gopls` - Language server
- `staticcheck` - Linter
- `gotest` - Test runner
- `dlv` - Debugger

Or install manually:

```bash
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
go install github.com/go-delve/delve/cmd/dlv@latest
```

## Opening the Project

### ✅ Recommended: Use VSC Workspace File

The workspace file is already created at `.vscode/cert-parser.code-workspace`:

```bash
# From project root
code .vscode/cert-parser.code-workspace
```

**This opens:**
- 🐍 cert-parser (Python) - Main application (`src/cert_parser/`)
- 🔧 Dagger Go Pipeline - CI/CD orchestration (`dagger_go/`)
- 📄 Deployment - Kubernetes configs
- 🧪 Tests - pytest unit/integration/acceptance

**Advantages:**
- All folders in one workspace ✅
- Shared settings for Python + Go ✅
- Easy navigation between modules ✅
- Tasks run in correct context ✅

### Option 1: Open Just dagger_go Folder

```bash
# From project root
code dagger_go/
```

Suitable for Go-only development.

### Option 2: Open Parent Directory

```bash
# From project root
code .
```

Opens entire workspace as root folder. Less organized but works.

## Development Workflow

### File Navigation

| Shortcut | Action |
|----------|--------|
| **Ctrl+P** | Quick file open |
| **Ctrl+Shift+P** | Command palette |
| **Ctrl+`** | Toggle terminal |
| **Ctrl+B** | Toggle sidebar |
| **Ctrl+Shift+E** | File explorer |
| **Ctrl+Shift+D** | Debugger |
| **Ctrl+Shift+T** | Open recent file |

### Code Editing

```bash
# Quick actions
Ctrl+Space          # Autocomplete
Alt+Enter           # Quick fix
F12                 # Go to definition
Ctrl+Shift+O        # Go to symbol
Ctrl+H              # Find and replace
```

### Testing

#### Run All Tests

```bash
Ctrl+Shift+P → Go: Test All
# OR
open terminal → go test -v
```

#### Run Single Test

```bash
# Right-click test function → Go: Run Test
# OR place cursor on test → Ctrl+Shift+P → Go: Test Function
```

#### View Test Results

```
Bottom panel → Test Results tab
```

## Running the Dagger Go Pipeline

### From Integrated Terminal

```bash
# Open terminal
Ctrl+`

# Navigate to dagger_go
cd dagger_go

# Run tests
./test.sh

# Run full pipeline
export CR_PAT="your-token"
export USERNAME="your-username"
./run.sh
```

### Create VSC Task

The `.vscode/tasks.json` is already configured to load credentials from `credentials/.env`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Test Dagger Go",
      "type": "shell",
      "command": "set -a && source ${workspaceFolder}/credentials/.env && set +a && cd ${workspaceFolder}/dagger_go && ./test.sh",
      "group": {
        "kind": "test",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "Build Railway Image",
      "type": "shell",
      "command": "cd ${workspaceFolder}/dagger_go && go build -o cert-parser-dagger-go main.go",
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "problemMatcher": ["$go"]
    },
    {
      "label": "Run Dagger Pipeline",
      "type": "shell",
      "command": "set -a && source ${workspaceFolder}/credentials/.env && set +a && cd ${workspaceFolder}/dagger_go && ./run.sh",
      "group": "build",
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    }
  ]
}
```

The tasks automatically load `CR_PAT` and `USERNAME` from your `credentials/.env` file. No manual prompts needed!

Run tasks:

```
Ctrl+Shift+P → Tasks: Run Task → Select task
```

### Create VSC Launch Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Dagger Go",
      "type": "go",
      "request": "launch",
      "mode": "debug",
      "program": "${workspaceFolder}/dagger_go",
      "env": {
        "CR_PAT": "${input:token}",
        "USERNAME": "${input:username}"
      },
      "args": [],
      "showLog": true,
      "trace": "verbose",
      "logOutput": "rpc"
    },
    {
      "name": "Test Dagger Go",
      "type": "go",
      "request": "launch",
      "mode": "test",
      "program": "${workspaceFolder}/dagger_go",
      "args": ["-test.v"],
      "showLog": true
    }
  ],
  "inputs": [
    {
      "id": "token",
      "description": "GitHub Token",
      "type": "promptString",
      "password": true
    },
    {
      "id": "username",
      "description": "GitHub Username",
      "type": "promptString"
    }
  ]
}
```

Then debug:

```
F5 → Select "Debug Dagger Go"
```

## Debugging

### Set Breakpoints

```
Click left margin next to line number
```

### Conditional Breakpoints

```
Right-click breakpoint → Edit Breakpoint
Enter condition: len(latestCommit) > 5
```

### Debug Console

```
Ctrl+Shift+D → Debug Console tab
Type: latestCommit (inspect variable)
```

### Debug Variables

Left panel shows:
- **Locals**: Local variables
- **Watch**: Monitored expressions
- **Call Stack**: Function call trace

### Step Through Code

| Shortcut | Action |
|----------|--------|
| **F10** | Step over |
| **F11** | Step into |
| **Shift+F11** | Step out |
| **F5** | Continue |
| **Shift+F5** | Stop |

## Code Quality Tools

### Format Code

```bash
# Automatic on save (configured above)
Ctrl+Shift+X → Right-click file → Format Document
```

### Lint Code

```
Ctrl+Shift+P → Go: Lint Package
```

Issues appear in Problems panel:

```
Ctrl+Shift+M → Problems tab
```

### Run Tests with Coverage

```bash
# Terminal
cd dagger_go
go test -cover

# View coverage
go test -coverprofile=coverage.out
go tool cover -html=coverage.out
```

## Environment Variables

### ✅ Recommended: Use credentials/.env

Your credentials are already set up in `credentials/.env`. The tasks automatically load them:

```bash
# No configuration needed - tasks load from credentials/.env automatically
set -a && source ${workspaceFolder}/credentials/.env && set +a
```

This loads `CR_PAT` and `USERNAME` for all tasks.

### Option 1: Load in Terminal

For manual terminal usage:

```bash
# In VSC terminal (Ctrl+`)
set -a
source credentials/.env
set +a

# Now run commands
cd dagger_go
./run.sh
```

### Option 2: VSC Settings

Add to `.vscode/settings.json`:

```json
{
  "terminal.integrated.env.linux": {
    "CR_PAT": "${env:CR_PAT}",
    "USERNAME": "${env:USERNAME}"
  }
}
```

### Option 3: Shell Profile

Add to `~/.zshrc` or `~/.bash_profile`:

```bash
export CR_PAT="ghp_xxxxxxxxxxxx"
export USERNAME="your-github-username"
```

## Project Structure in VSC

### Explorer View

```
cert-parser (Workspace)
├── dagger_go/
│   ├── main.go
│   ├── main_test.go
│   ├── go.mod
│   ├── test.sh
│   └── run.sh
├── python_framework/
│   ├── pom.xml
│   └── src/
├── .vscode/
│   ├── tasks.json
│   ├── launch.json
│   └── settings.json
└── deployment/
    └── ...
```

### Outline View

Shows structure of current file:

```
Ctrl+Shift+O → Outline panel
```

For `main.go`, shows:
- Functions
- Types
- Methods

## IntelliSense & Autocomplete

### Basic Autocomplete

```go
client := dagger.Con|  // Type to see suggestions
```

Suggestions appear automatically. Select with:
- **Enter** - Accept suggestion
- **Esc** - Dismiss
- **Ctrl+Space** - Manual trigger

### Go-to Definition

```go
dagger.Container{} // Ctrl+click Container
// or F12
// Opens dagger package definition
```

### Find References

```
Ctrl+Shift+H → Find All References
Right-click symbol → Go to References
```

### Rename Symbol

```
F2 → Type new name → Enter
// Renames all occurrences
```

## Extensions for Go Development

### Code Generation

**GoGen** - Generate code from templates

```
Ctrl+Shift+P → GoGen: Generate
```

### Go Tests

**Go Test Explorer** - Visual test runner

```
Testing icon in sidebar → See all tests
```

### MongoDB/Database Tools (if needed)

**MongoDB for VSC**

```
code --install-extension MongoDB.mongodb-vscode
```

### REST Client

**REST Client** - Test APIs without Postman

```
code --install-extension humao.rest-client
```

Create `requests.http`:

```http
GET http://localhost:8080/api/v1/health
```

Then click "Send Request"

## Terminal Integration

### Built-in Terminal

```
Ctrl+` → Opens terminal in project root
```

Multiple terminals:

```
Ctrl+Shift+` → New terminal
```

### Terminal Profiles

Configure in `.vscode/settings.json`:

```json
{
  "terminal.integrated.profiles.osx": {
    "zsh": {
      "path": "/bin/zsh",
      "args": ["-l"]
    },
    "bash": {
      "path": "/bin/bash"
    }
  },
  "terminal.integrated.defaultProfile.osx": "zsh"
}
```

## Performance Optimization

### Disable Unnecessary Features

Add to `.vscode/settings.json`:

```json
{
  "go.diagnostic.semanticTokens": false,
  "go.lintOnSave": "off",  // Run manually instead
  "[go]": {
    "editor.formatOnSave": false  // Format manually
  }
}
```

### Exclude Large Directories

```json
{
  "files.exclude": {
    "**/node_modules": true,
    "**/target": true,
    "**/.git": true
  },
  "search.exclude": {
    "**/vendor": true,
    "**/node_modules": true
  }
}
```

## Troubleshooting

### Go Tools Not Found

```bash
# Error: "Go installation not found"
# Solution:
which go
# Should return: /usr/local/go/bin/go

# Add to PATH if needed
export PATH=$PATH:/usr/local/go/bin
```

### Language Server Issues

```
Ctrl+Shift+P → Go: Install/Update Tools
Accept all prompts
```

### Debugging Not Working

```bash
# Install dlv explicitly
go install github.com/go-delve/delve/cmd/dlv@latest

# Verify
dlv version
```

### Module Not Found

```
Ctrl+Shift+P → Go: Get Dependencies
go mod download
go mod tidy
```

### Format Not Working

```bash
# Ensure goimports is installed
go install golang.org/x/tools/cmd/goimports@latest

# Force format
Ctrl+Shift+P → Format Document
```

## Useful Extensions Combo

### Development Setup

```bash
# Install all recommended extensions at once
code --install-extension golang.go \
     --install-extension ms-azuretools.vscode-docker \
     --install-extension usernamehw.errorlens \
     --install-extension ms-vscode.makefile-tools \
     --install-extension GitHub.copilot
```

### Recommended Extensions

| Extension | Purpose | Command |
|-----------|---------|---------|
| **Go** | Go development | `golang.go` |
| **Docker** | Container files | `ms-azuretools.vscode-docker` |
| **Error Lens** | Inline errors | `usernamehw.errorlens` |
| **Makefile Tools** | Build support | `ms-vscode.makefile-tools` |
| **GitHub Copilot** | AI assistant | `github.copilot` |
| **GitLens** | Git tracking | `eamodio.gitlens` |
| **Thunder Client** | API testing | `rangav.vscode-thunder-client` |

## Complete Setup Script

Create `setup-vsc.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Setting up VSC for Railway Dagger Go..."

# Install Go tools
echo "📦 Installing Go tools..."
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
go install github.com/go-delve/delve/cmd/dlv@latest

# Install VSC extensions
echo "📥 Installing VSC extensions..."
code --install-extension golang.go
code --install-extension ms-azuretools.vscode-docker
code --install-extension usernamehw.errorlens
code --install-extension ms-vscode.makefile-tools

# Create workspace file
echo "📝 Creating workspace configuration..."
mkdir -p .vscode
# tasks.json, launch.json, settings.json created above

# Set permissions on scripts
echo "🔐 Setting script permissions..."
chmod +x dagger_go/test.sh
chmod +x dagger_go/run.sh

echo "✅ VSC setup complete!"
echo ""
echo "📖 Next steps:"
echo "   1. Open VSC: code ."
echo "   2. Install recommended extensions"
echo "   3. Configure CR_PAT and USERNAME in terminal"
echo "   4. Run: Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go"
```

Run:

```bash
bash setup-vsc.sh
```

## Keyboard Shortcuts Cheat Sheet

| Shortcut | Action |
|----------|--------|
| **Ctrl+P** | Quick file open |
| **Ctrl+`** | Toggle terminal |
| **Ctrl+Space** | Autocomplete |
| **F12** | Go to definition |
| **Shift+F12** | Find references |
| **F2** | Rename symbol |
| **Ctrl+Shift+P** | Command palette |
| **Ctrl+Shift+E** | Explorer |
| **Ctrl+Shift+D** | Debugger |
| **Ctrl+Shift+M** | Problems |
| **F5** | Debug/Continue |
| **F10** | Step over |
| **F11** | Step into |

## Next Steps

1. ✅ Install VSC
2. ✅ Install Go extensions
3. ✅ Open workspace file
4. ✅ Credentials automatically loaded
5. ✅ Run pipeline with one click

## Quick Start: Build & Run

### Fastest Way: Using VSC Tasks (Recommended)

**All credentials loaded automatically from `credentials/.env`**

#### Step 1: Open Workspace

```bash
# From project root
code .vscode/cert-parser.code-workspace
```

#### Step 2: Run Test Task

```
Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go
```

- Loads `credentials/.env` automatically ✅
- Runs `go mod download` ✅
- Compiles and tests the code ✅
- Shows results in integrated terminal ✅

#### Step 3: Build Binary

```
Ctrl+Shift+P → Tasks: Run Task → Build Railway Image
```

- Compiles Go code to `cert-parser-dagger-go` executable
- Ready for deployment

#### Step 4: Run Full Pipeline

```
Ctrl+Shift+P → Tasks: Run Task → Run Dagger Pipeline
```

- Loads `credentials/.env` automatically ✅
- Builds Docker image ✅
- Pushes to GitHub Container Registry ✅
- Deploys to Kubernetes (if configured) ✅

**That's it! No manual credential configuration needed.**

---

### Manual Terminal Approach

If you prefer the integrated terminal:

#### Step 1: Load Credentials

```bash
# Open terminal: Ctrl+`
set -a
source credentials/.env
set +a

# Verify loaded
echo $CR_PAT
echo $USERNAME
```

#### Step 2: Run Tests

```bash
cd dagger_go
./test.sh
```

Expected output:
```
✓ Project discovery working
✓ Environment variables loaded
✓ Go build successful
```

#### Step 3: Build Binary

```bash
go build -o cert-parser-dagger-go main.go
```

Binary created: `cert-parser-dagger-go` (15MB)

#### Step 4: Run Pipeline

```bash
./run.sh
```

Expected output:
```
🚀 Starting Python CI/CD Pipeline (Go SDK v0.19.7)...
🐍 Installing Python dependencies...
🧪 Running unit tests... ✅ 111 passed
🔍 Running lint (ruff)... ✅ No issues
🔍 Running type check (mypy)... ✅ 0 errors
🐳 Building Docker image...
📤 Pushing to registry...
✅ Pipeline completed successfully
```

---

### Debug Mode: Using F5

Start debugging with full breakpoint support:

1. **Set breakpoint** - Click left margin in `main.go`
2. **Start debug** - Press `F5` → Select "Debug Dagger Go"
3. **Step through code** - Use F10/F11
4. **Inspect variables** - Left panel shows locals, watches, call stack
5. **Stop** - Press Shift+F5

Credentials loaded automatically for debug sessions.

---

## Project Files Location

| File | Purpose | Created |
|------|---------|---------|
| **dagger_go/main.go** | CI/CD pipeline implementation | ✅ |
| **dagger_go/main_test.go** | Unit tests | ✅ |
| **dagger_go/go.mod** | Go module definition | ✅ |
| **dagger_go/test.sh** | Test runner script | ✅ |
| **dagger_go/run.sh** | Production runner script | ✅ |
| **.vscode/tasks.json** | VSC build/run tasks | ✅ |
| **.vscode/launch.json** | VSC debug configurations | ✅ |
| **.vscode/settings.json** | VSC editor settings | ✅ |
| **.vscode/cert-parser.code-workspace** | Multi-folder workspace | ✅ |
| **credentials/.env** | GitHub credentials | ✅ (your file) |

All configuration files are in place. Ready to use!

---

## Build Artifacts

After successful build:

```
cert-parser-dagger-go          # Compiled binary (15MB)
cert-parser-dagger-go.md5      # Checksum file
coverage.out               # Test coverage data
```

---

## Environment Verification

### Verify Go Installation

```bash
go version
# Expected: go version go1.22+
```

### Verify Dagger CLI

```bash
dagger version
# Expected: dagger v0.19.7
```

### Verify Docker

```bash
docker --version
# Expected: Docker version 20.10+

docker ps
# Should list running containers
```

### Verify Credentials

Credentials are automatically loaded from `credentials/.env`:

```bash
# Manually verify in terminal
set -a && source credentials/.env && set +a
echo "PAT: $CR_PAT"
echo "User: $USERNAME"
```

---

## What Each Task Does

### Task: Test Dagger Go

```bash
# Executed command:
set -a && source ${workspaceFolder}/credentials/.env && set +a && \
cd ${workspaceFolder}/dagger_go && ./test.sh
```

**Actions:**
1. Loads credentials from `credentials/.env`
2. Navigates to `dagger_go/` directory
3. Runs `test.sh` which:
   - Validates Go installation
   - Downloads module dependencies (`go mod download`)
   - Runs unit tests (`go test -v`)
   - Compiles test binary

**Expected duration:** 30-60 seconds

**Success indicator:**
```
ok      railway/dagger    0.234s
PASS
```

### Task: Build Railway Image

```bash
# Executed command:
cd ${workspaceFolder}/dagger_go && go build -o cert-parser-dagger-go main.go
```

**Actions:**
1. Compiles Go source code to executable
2. Creates `cert-parser-dagger-go` binary (15MB)
3. Single-file deployment ready

**Expected duration:** 5-10 seconds

**Success indicator:**
```
$ ls -lh cert-parser-dagger-go
-rwxr-xr-x  cert-parser-dagger-go (15M)
```

### Task: Run Dagger Pipeline

```bash
# Executed command:
set -a && source ${workspaceFolder}/credentials/.env && set +a && \
cd ${workspaceFolder}/dagger_go && ./run.sh
```

**Actions:**
1. Loads credentials (`CR_PAT`, `USERNAME`) — and optionally `GIT_HOST`, `REGISTRY`
2. Validates Docker daemon running
3. Executes full CI/CD pipeline:
   - Discovers Python project name from `pyproject.toml`
   - Installs `python_framework` (railway-rop) then project with `.[dev,server]`
   - Runs `pytest` unit/integration/acceptance tests
   - Lints with `ruff`, type-checks with `mypy`
   - Creates Docker image from `Dockerfile`
   - Tags with git SHA
   - Pushes to the configured container registry
   - Logs to CloudWatch (if configured)
   - Cleans up temporary resources

**Expected duration:** 3-5 minutes (first run), 1-2 minutes (cached)

**Success indicator:**
```
✅ Pipeline completed successfully
Image pushed to ghcr.io/username/python_framework:abc1234def
```

---

## Common Workflows

### Workflow 1: Local Development

```bash
# 1. Make code changes in main.go
# 2. Test immediately
Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go

# 3. View results in integrated terminal
# 4. Debug if needed
F5 → Debug Dagger Go
```

### Workflow 2: Build for Deployment

```bash
# 1. Build binary
Ctrl+Shift+P → Tasks: Run Task → Build Railway Image

# 2. Verify binary created
ls -lh cert-parser-dagger-go

# 3. Deploy to server
scp cert-parser-dagger-go user@server:/opt/cert-parser/
```

### Workflow 3: Full CI/CD Pipeline

```bash
# 1. Test locally
Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go

# 2. Build image
Ctrl+Shift+P → Tasks: Run Task → Build Railway Image

# 3. Run full pipeline (builds Docker, pushes to registry)
Ctrl+Shift+P → Tasks: Run Task → Run Dagger Pipeline
```

### Workflow 4: Debug Production Issue

```bash
# 1. Set breakpoint in main.go
# 2. Set environment for production
set -a && source credentials/.env && set +a

# 3. Debug with F5
F5 → Test Dagger Go

# 4. Inspect variables, check logic
# 5. Fix issue, rebuild
```

---

## Troubleshooting Build Issues

### Problem: "Command not found: go"

```bash
# Solution: Verify Go installation
which go
# Should show: /usr/local/go/bin/go

# Add to PATH if needed
export PATH=$PATH:/usr/local/go/bin
```

### Problem: "Module not found"

```bash
# Solution: Download dependencies
cd dagger_go
go mod download
go mod tidy
```

### Problem: "credentials/.env not found"

```bash
# Solution: Create .env file in credentials directory
cat > credentials/.env << EOF
CR_PAT=ghp_xxxxxxxxxxxx
USERNAME=your-github-username
EOF

# Then reload in terminal
set -a && source credentials/.env && set +a
```

### Problem: "Docker daemon not running"

```bash
# Solution: Start Docker
docker ps
# If error, start Docker Desktop or daemon:
sudo service docker start
```

### Problem: Task won't execute

```bash
# Solution 1: Reload VSC
Cmd+Shift+P → Reload Window

# Solution 2: Verify tasks.json exists
ls -la .vscode/tasks.json

# Solution 3: Check permissions
chmod +x dagger_go/test.sh
chmod +x dagger_go/run.sh
```

### Problem: "No such file or directory: ./test.sh"

```bash
# Solution: Make scripts executable
chmod +x dagger_go/test.sh
chmod +x dagger_go/run.sh

# Then retry task
Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go
```

---

## Performance Tips

### Speed Up Builds

1. **Use existing binary** - Build once, reuse multiple times
2. **Enable Go caching** - `go env -w GOCACHE=$HOME/.cache/go-build`
3. **Use modules cache** - `go mod download` pre-caches all dependencies
4. **Parallel testing** - `go test -parallel 4`

### Optimize IDE

1. Disable semantic tokens:
   ```json
   "go.diagnostic.semanticTokens": false
   ```

2. Run linting manually instead of on-save:
   ```json
   "go.lintOnSave": "off"
   ```

3. Exclude large directories:
   ```json
   "search.exclude": {
     "**/vendor": true,
     "**/target": true
   }
   ```

---

## Resources

- 📖 [VSC Go Guide](https://github.com/golang/vscode-go/wiki)
- 🔗 [Go Language Support](https://code.visualstudio.com/docs/languages/go)
- 💬 [VSC Docs](https://code.visualstudio.com/docs)
- 🐙 [Go Delve Debugger](https://github.com/go-delve/delve)
- 🔧 [Dagger Go SDK](./DAGGER_GO_SDK.md)
- 📋 [Quick Start Guide](./QUICKSTART.md)

---

## Validation Checklist

Before running pipelines, verify:

- [ ] VSC installed and Go extension active
- [ ] Go 1.22+ installed (`go version`)
- [ ] Dagger CLI v0.19.7+ installed (`dagger version`)
- [ ] Docker running (`docker ps` works)
- [ ] `credentials/.env` exists with `CR_PAT` and `USERNAME`
- [ ] All `.vscode/` config files in place
- [ ] `dagger_go/test.sh` and `run.sh` are executable
- [ ] Network connection to GitHub Container Registry

**All checks passing? Ready to build and deploy! ✅**

---

**Next Steps:**

1. Open workspace: `code .vscode/cert-parser.code-workspace`
2. Run test task: `Ctrl+Shift+P → Tasks: Run Task → Test Dagger Go`
3. Build binary: `Ctrl+Shift+P → Tasks: Run Task → Build Railway Image`
4. Run pipeline: `Ctrl+Shift+P → Tasks: Run Task → Run Dagger Pipeline`

---
