````markdown
# Local Development Setup — cert-parser

> **Audience**: A developer who is brand new to this project, possibly to Python 3.14,
> PyCharm, and VS Code. Follow this guide top-to-bottom and you will have a fully
> working development environment.
>
> **Covers**: Windows 10/11 and Ubuntu/Debian Linux (same Python source, different tooling steps).

---

## Table of Contents

1. [Prerequisites — What You Need First](#1-prerequisites--what-you-need-first)
   - 1.1 [Windows](#11-windows)
   - 1.2 [Ubuntu / Linux](#12-ubuntu--linux)
2. [Get the Code](#2-get-the-code)
3. [Create the Virtual Environment (`.venv`)](#3-create-the-virtual-environment-venv)
4. [Install Dependencies](#4-install-dependencies)
5. [Configure the Application (`.env`)](#5-configure-the-application-env)
6. [Run the Application Locally](#6-run-the-application-locally)
7. [Run the Tests](#7-run-the-tests)
8. [IDE Setup — PyCharm](#8-ide-setup--pycharm)
   - 8.1 [Install PyCharm](#81-install-pycharm)
   - 8.2 [Open the Project](#82-open-the-project)
   - 8.3 [Configure the Interpreter (point to `.venv`)](#83-configure-the-interpreter-point-to-venv)
   - 8.4 [Configure Run/Debug for `asgi.py`](#84-configure-rundebug-for-asgipy)
   - 8.5 [Configure the Test Runner](#85-configure-the-test-runner)
   - 8.6 [Verify Linting and Type Checking in PyCharm](#86-verify-linting-and-type-checking-in-pycharm)
9. [IDE Setup — VS Code](#9-ide-setup--vs-code)
   - 9.1 [Install VS Code](#91-install-vs-code)
   - 9.2 [Install Required Extensions](#92-install-required-extensions)
   - 9.3 [Open the Project and Select the Interpreter](#93-open-the-project-and-select-the-interpreter)
   - 9.4 [Configure Launch (Run/Debug) for `asgi.py`](#94-configure-launch-rundebug-for-asgipy)
   - 9.5 [Configure the Test Runner](#95-configure-the-test-runner)
10. [Daily Development Workflow](#10-daily-development-workflow)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites — What You Need First

### 1.1 Windows

#### Python 3.14+

This project **requires Python 3.14** (for PEP 758 bare-comma `except` and `type` alias syntax).

1. Go to **https://www.python.org/downloads/windows/** and download the latest **Python 3.14.x** installer.
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"** — this is important.
3. Choose **"Customize installation"**, tick "pip", "tcl/tk", "py launcher", then proceed.
4. Complete the installation.

Verify in a new **Command Prompt** (`Win + R` → `cmd`):

```cmd
python --version
```

Expected output: `Python 3.14.x`

> **If you have an older Python**: The `py` launcher lets you have multiple Python versions
> side-by-side. Use `py -3.14` instead of `python` in all commands below.

#### Git

1. Download from **https://git-scm.com/download/win**
2. Accept defaults during installation. Make sure "Git from the command line" is selected.

Verify:

```cmd
git --version
```

#### PostgreSQL (for integration/acceptance tests only)

Integration tests use [testcontainers](https://testcontainers.com/) which spins up a temporary
Docker container — you only need Docker for that (see below). For running the **application**
itself you need a real PostgreSQL instance (local or remote).

Option A — Install PostgreSQL locally:
- Download from **https://www.postgresql.org/download/windows/**
- Default port: 5432

Option B — Use the database from the simulator (if `prt_services_simulator` is already running nearby).

#### Docker Desktop (for integration tests)

Required only if you want to run `pytest -m integration` or `pytest -m acceptance`.

Download from **https://www.docker.com/products/docker-desktop/** and install. Start Docker Desktop and make sure the Docker icon shows "running" in the system tray.

---

### 1.2 Ubuntu / Linux

#### Python 3.14+

Python 3.14 may not be in the default Ubuntu apt repository yet. Use the **deadsnakes PPA**:

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.14 python3.14-venv python3.14-dev
```

Verify:

```bash
python3.14 --version
```

Expected: `Python 3.14.x`

> **Tip**: The project needs `python3.14-venv` to create virtual environments. If you skip
> installing it the `python -m venv` command will fail with a clear error.

#### Git

```bash
sudo apt install -y git
git --version
```

#### Build Tools (needed by `cryptography` and `psycopg` binary wheels)

```bash
sudo apt install -y build-essential libpq-dev libssl-dev libffi-dev
```

#### Docker (for integration tests)

Follow the official guide for your distro:
**https://docs.docker.com/engine/install/ubuntu/**

After installing, add your user to the `docker` group so you can run containers without `sudo`:

```bash
sudo usermod -aG docker $USER
newgrp docker          # apply immediately (or log out/in)
docker --version       # verify
```

---

## 2. Get the Code

Clone the repository (replace the URL with the actual remote):

```bash
# Linux/macOS
git clone https://github.com/your-org/cert-parser.git
cd cert-parser

# Windows (Command Prompt or PowerShell)
git clone https://github.com/your-org/cert-parser.git
cd cert-parser
```

The repository contains a **local framework** under `python_framework/`. This is a local Python
package called `railway-rop` that must be installed alongside the main project. The structure is:

```
cert-parser/
├── python_framework/   ← local railway-rop package (install first)
├── src/cert_parser/    ← application source code
├── tests/              ← test suite
├── pyproject.toml      ← project metadata + dependencies
└── .env.example        ← configuration template → copy to .env
```

---

## 3. Create the Virtual Environment (`.venv`)

A virtual environment isolates this project's Python and packages from everything else on your
machine. **Nothing is installed globally.**

### Windows

```cmd
REM Navigate to the project root (where pyproject.toml lives)
cd C:\path\to\cert-parser

REM Create the virtual environment using Python 3.14
python -m venv .venv
REM Or, if you have multiple Python versions:
py -3.14 -m venv .venv

REM Activate it
.venv\Scripts\activate

REM Your prompt now shows (.venv) — all pip commands affect only this environment
```

### Ubuntu / Linux

```bash
cd /path/to/cert-parser

# Create the virtual environment
python3.14 -m venv .venv

# Activate it
source .venv/bin/activate

# Your prompt now shows (.venv)
```

> **Important**: You must activate the virtual environment every time you open a new terminal.
> Both PyCharm and VS Code can do this automatically (configured in sections 8 and 9).

---

## 4. Install Dependencies

The project has **two install steps** because `railway-rop` is a local package that must be
installed before the main project (which depends on it).

With the virtual environment **activated** (you should see `(.venv)` in your prompt):

```bash
# Step 1 — install the local railway-rop framework
pip install -e "./python_framework"

# Step 2 — install the application + all dev and server dependencies
pip install -e ".[dev,server]"
```

`-e` means "editable install" — changes you make to the source are reflected immediately without
reinstalling.

**What gets installed:**

| Group | Packages | Purpose |
|-------|----------|---------|
| Core | `httpx`, `asn1crypto`, `cryptography`, `psycopg`, `APScheduler`, `pydantic-settings`, `tenacity`, `structlog` | Application runtime |
| `server` | `uvicorn`, `fastapi` | ASGI web server + framework |
| `dev` | `pytest`, `mypy`, `ruff`, `respx`, `testcontainers` | Testing and linting tools |

Verify the installation:

```bash
python -c "import cert_parser; print('OK')"
python -c "from railway.result import Result; print('railway-rop OK')"
```

Both should print without errors.

---

## 5. Configure the Application (`.env`)

The application is configured via environment variables. For local development, you use a `.env`
file in the project root.

```bash
# Copy the example template
cp .env.example .env     # Linux/Mac
copy .env.example .env   # Windows CMD
```

Now edit `.env` and fill in the real values. The file uses the `__` double-underscore delimiter
to map to nested settings (e.g., `AUTH__URL` maps to `auth.url` in code):

```dotenv
# ── Step 1: OpenID Connect Authentication ─────────────────────────────────────
AUTH__URL=http://localhost:8087/protocol/openid-connect/token
AUTH__CLIENT_ID=your-client-id
AUTH__CLIENT_SECRET=your-client-secret
AUTH__USERNAME=your-username
AUTH__PASSWORD=your-password

# ── Step 2: SFC Login ──────────────────────────────────────────────────────────
LOGIN__URL=http://localhost:8087/auth/v1/login
LOGIN__BORDER_POST_ID=1
LOGIN__BOX_ID=XX/99/X
LOGIN__PASSENGER_CONTROL_TYPE=1

# ── Step 3: Certificate Download ───────────────────────────────────────────────
DOWNLOAD__URL=http://localhost:8087/certificates/csca

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE__HOST=localhost
DATABASE__PORT=5432
DATABASE__NAME=postgres
DATABASE__USERNAME=postgres
DATABASE__PASSWORD=postgres

# ── Scheduler (cron: every 6 hours) ───────────────────────────────────────────
SCHEDULER__CRON=0 */6 * * *

# ── Application ────────────────────────────────────────────────────────────────
HTTP_TIMEOUT_SECONDS=60
RUN_ON_STARTUP=true
LOG_LEVEL=INFO
```

> ⚠️ **Never commit `.env`** — it is in `.gitignore`. It contains credentials.

---

## 6. Run the Application Locally

The application runs as an ASGI web service using **Uvicorn**. Once running, it:
- Starts a background scheduler that triggers the pipeline on the cron schedule
- Exposes HTTP endpoints for health checks (`/health`, `/ready`) and manual trigger (`POST /trigger`)

With the virtual environment activated and `.env` configured:

```bash
# Run via uvicorn (recommended — matches production Dockerfile)
python -m uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1

# Or via the CLI entry point (equivalent)
cert-parser
```

You should see structlog output like:

```
2026-03-04T10:00:00Z [info] asgi.startup
2026-03-04T10:00:00Z [info] asgi.startup_config version=0.1.0 cron="0 */6 * * *"
2026-03-04T10:00:00Z [info] asgi.startup_complete
```

**Test the endpoints** (in a second terminal):

```bash
curl http://localhost:8000/health
# → {"status":"healthy","scheduler_running":true}

curl http://localhost:8000/ready
# → {"status":"ready","scheduler_running":true}

curl http://localhost:8000/info
# → {"name":"cert-parser","version":"0.1.0",...}

# Manually trigger the full pipeline (auth → download → parse → store):
curl -X POST http://localhost:8000/trigger
# → {"status":"success","rows_stored":278}
```

> **Root path / API gateway**: If you run behind an API gateway with a prefix (e.g., `/cert-parser`),
> set the `ROOT_PATH` environment variable:
>
> ```bash
> ROOT_PATH=/cert-parser python -m uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000
> ```
>
> See [Configuration Guide](../CONFIGURATION_GUIDE.md) for details.

---

## 7. Run the Tests

### Unit Tests (fast, no database, no Docker)

```bash
pytest tests/unit/ -v
```

### Integration Tests (require Docker — testcontainers spins up PostgreSQL)

```bash
pytest tests/integration/ -v -m integration
```

### Acceptance Tests (require Docker)

```bash
pytest tests/acceptance/ -v -m acceptance
```

### All Unit Tests with Coverage Report

```bash
pytest tests/unit/ --cov=cert_parser --cov-report=term-missing
```

### Linting and Type Checking

```bash
# Linting (ruff)
ruff check src/ tests/ scripts/

# Formatting check (ruff)
ruff format --check src/ tests/

# Auto-fix formatting
ruff format src/ tests/

# Type checking (mypy strict mode)
mypy src/ --strict
```

---

## 8. IDE Setup — PyCharm

### 8.1 Install PyCharm

#### Windows

1. Download **PyCharm Community** (free) or **Professional** from
   **https://www.jetbrains.com/pycharm/download/**
2. Run the installer. Accept defaults.
3. During installation, tick:
   - ✅ "Add 'bin' folder to the PATH"
   - ✅ "Create Desktop shortcut"
   - ✅ ".py" file association

#### Ubuntu / Linux

Option A — JetBrains Toolbox (recommended, manages updates automatically):

```bash
# Download the Toolbox installer from https://www.jetbrains.com/toolbox-app/
chmod +x jetbrains-toolbox-*.AppImage
./jetbrains-toolbox-*.AppImage
# In the Toolbox UI, click "Install" next to PyCharm Community
```

Option B — Snap:

```bash
sudo snap install pycharm-community --classic
```

---

### 8.2 Open the Project

1. Launch PyCharm
2. Click **"Open"** on the welcome screen (or `File → Open`)
3. Navigate to the `cert-parser` folder (the one with `pyproject.toml`) and click **OK**
4. PyCharm will index the project. Wait for the progress bar at the bottom to finish.

---

### 8.3 Configure the Interpreter (point to `.venv`)

PyCharm must use the virtual environment you created in step 3 — NOT the system Python.

1. Go to **`File → Settings`** (Windows/Linux) or **`PyCharm → Preferences`** (macOS)
2. Navigate to **`Project: cert-parser → Python Interpreter`**
3. Click the gear icon ⚙ next to the interpreter dropdown → **"Add Interpreter"**
4. Select **"Existing environment"**
5. Click the `...` button and browse to:
   - **Windows**: `C:\path\to\cert-parser\.venv\Scripts\python.exe`
   - **Linux/Mac**: `/path/to/cert-parser/.venv/bin/python`
6. Click **OK** → **Apply** → **OK**

After a few seconds, PyCharm will index the `.venv` packages. You should see all imports resolve
(no red underlines in `main.py`, `asgi.py`, etc.).

> **Quick check**: Open `src/cert_parser/main.py`. If `from cert_parser.config import AppSettings`
> shows no red squiggles, the interpreter is correctly configured.

#### Mark Source Roots

PyCharm needs to know where the source code lives:

1. Right-click on `src/` folder in the Project panel → **"Mark Directory as" → "Sources Root"**
2. Right-click on `python_framework/src/` → **"Mark Directory as" → "Sources Root"**
3. Right-click on `tests/` → **"Mark Directory as" → "Test Sources Root"**

This eliminates the "Unresolved reference" warnings for `cert_parser` and `railway` imports.

---

### 8.4 Configure Run/Debug for `asgi.py`

Create a run configuration to launch the ASGI server from within PyCharm:

1. Click **`Run → Edit Configurations`** (or the dropdown at the top right → **"Edit Configurations"**)
2. Click **`+`** → **"Python"**
3. Fill in:

   | Field | Value |
   |-------|-------|
   | **Name** | `cert-parser (uvicorn)` |
   | **Module name** | `uvicorn` |
   | **Parameters** | `cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1` |
   | **Working directory** | `/path/to/cert-parser` |
   | **Environment variables** | *(leave empty — loaded from `.env` file automatically)* |
   | **Python interpreter** | `.venv` interpreter (should already be selected) |

4. Click **OK**

Now you can press the green **▶ Run** button (or `Shift+F10`) to start the server, and the red
**■ Stop** button to stop it.

For **debugging** (breakpoints, step-through), press the **🐛 Debug** button (`Shift+F9`).

> **Tip**: PyCharm's debugger works seamlessly with async code. You can set breakpoints inside
> FastAPI route handlers and step through them.

---

### 8.5 Configure the Test Runner

1. Go to **`File → Settings → Tools → Python Integrated Tools`**
2. Set **"Default test runner"** to **"pytest"**
3. Click **Apply → OK**

To run all unit tests:
- Right-click on the `tests/unit/` folder → **"Run pytest in tests/unit"**

To run a single test file:
- Open it → right-click anywhere → **"Run pytest in ..."**

To run with coverage:
- Right-click → **"Run pytest in ... with Coverage"**

---

### 8.6 Verify Linting and Type Checking in PyCharm

PyCharm has built-in inspections but `ruff` and `mypy` are the project standards.

**Install the ruff plugin** (optional but recommended):

1. `File → Settings → Plugins → Marketplace`
2. Search for **"Ruff"** → Install → Restart PyCharm

**Run mypy from the terminal** inside PyCharm (`Alt+F12` opens the integrated terminal):

```bash
mypy src/ --strict
```

---

## 9. IDE Setup — VS Code

### 9.1 Install VS Code

#### Windows

1. Download from **https://code.visualstudio.com/**
2. Run the installer. During installation, tick:
   - ✅ "Add to PATH"
   - ✅ "Register Code as an editor for supported file types"
   - ✅ "Add 'Open with Code' action to context menu"

#### Ubuntu / Linux

Option A — Official `.deb` package (recommended):

```bash
# Download from https://code.visualstudio.com/Download
sudo dpkg -i code_*.deb
sudo apt-get install -f   # fix any dependency issues
```

Option B — Snap:

```bash
sudo snap install --classic code
```

Verify installation:

```bash
code --version
```

---

### 9.2 Install Required Extensions

Open VS Code, then press `Ctrl+Shift+X` to open the Extensions panel.

Install these extensions:

| Extension | Publisher ID | Purpose |
|-----------|-------------|---------|
| **Python** | `ms-python.python` | Python language support, IntelliSense, debugging |
| **Pylance** | `ms-python.vscode-pylance` | Fast type-checking and IntelliSense (pairs with Python extension) |
| **Ruff** | `charliermarsh.ruff` | Linting and formatting (replaces flake8, black, isort) |
| **Mypy Type Checker** | `ms-python.mypy-type-checker` | mypy integration |

Install from the command line (alternative):

```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension charliermarsh.ruff
code --install-extension ms-python.mypy-type-checker
```

---

### 9.3 Open the Project and Select the Interpreter

1. `File → Open Folder` → select the `cert-parser` directory (where `pyproject.toml` lives)
2. VS Code may prompt "Do you trust the authors of this folder?" → click **"Yes, I trust the authors"**
3. Select the Python interpreter:
   - Press `Ctrl+Shift+P` → type **"Python: Select Interpreter"** → press Enter
   - VS Code should auto-detect `.venv` — select it (it shows `./.venv/bin/python`)
   - If it doesn't appear, click **"Enter interpreter path"** and browse to:
     - **Windows**: `.\.venv\Scripts\python.exe`
     - **Linux**: `./.venv/bin/python`

After selecting the interpreter, VS Code stores it in `.vscode/settings.json`. The status bar
at the bottom should show the Python version from `.venv`.

#### Configure `settings.json`

Create or edit `.vscode/settings.json` in the project root:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.analysis.extraPaths": [
        "${workspaceFolder}/src",
        "${workspaceFolder}/python_framework/src"
    ],
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests/unit"
    ],
    "ruff.enable": true,
    "ruff.organizeImports": true,
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "mypy-type-checker.args": [
        "--strict"
    ]
}
```

> **Windows note**: Use `${workspaceFolder}/.venv/Scripts/python.exe` for the interpreter path
> on Windows.

---

### 9.4 Configure Launch (Run/Debug) for `asgi.py`

Create `.vscode/launch.json` in the project root:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "cert-parser (uvicorn)",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "cert_parser.asgi:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--workers", "1"
            ],
            "env": {
                "PYTHONPATH": "${workspaceFolder}/src:${workspaceFolder}/python_framework/src"
            },
            "jinja": false,
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal"
        },
        {
            "name": "cert-parser (pytest unit)",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": [
                "tests/unit",
                "-v",
                "--tb=short"
            ],
            "env": {
                "PYTHONPATH": "${workspaceFolder}/src:${workspaceFolder}/python_framework/src"
            },
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal"
        }
    ]
}
```

Press `F5` to launch with debugging. Set breakpoints by clicking the gutter (left of line numbers).

---

### 9.5 Configure the Test Runner

VS Code discovers tests automatically from `settings.json`. To run tests:

- Click the **🧪 Testing** icon in the left sidebar
- Tests are organized by file and function
- Click the **▶ play** button next to any test or folder
- Click the **🐛 debug** icon to run a test in debug mode (breakpoints work here too)

---

## 10. Daily Development Workflow

Here is the typical flow for working on a feature:

```bash
# 1. Open a terminal and activate the venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 2. Pull latest changes
git pull

# 3. (If pyproject.toml changed) reinstall dependencies
pip install -e "./python_framework"
pip install -e ".[dev,server]"

# 4. Write a failing test first (TDD red phase)
# e.g., edit tests/unit/test_cms_parser.py

# 5. Run the test — expect it to fail
pytest tests/unit/test_cms_parser.py::test_your_new_test -v

# 6. Write the minimal production code to make it pass

# 7. Run tests again — expect green
pytest tests/unit/ -v

# 8. Check linting and types
ruff check src/ tests/
mypy src/ --strict

# 9. Start the ASGI app and test manually if needed
python -m uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1

# 10. Commit
git add -p
git commit -m "feat: describe what you did"
```

---

## 11. Troubleshooting

### "Unresolved reference 'cert_parser'" in PyCharm

**Cause**: PyCharm does not know that `src/` is a source root.

**Fix**: Right-click `src/` → "Mark Directory as" → "Sources Root". Also right-click
`python_framework/src/` → "Sources Root".

---

### "Unresolved reference 'railway'" in PyCharm / VS Code

**Cause**: `railway-rop` was not installed in the venv, or the wrong interpreter is selected.

**Fix**:

```bash
source .venv/bin/activate
pip install -e "./python_framework"
python -c "from railway.result import Result; print('OK')"
```

Then ensure the IDE is using the `.venv` interpreter (sections 8.3 and 9.3).

---

### "FATAL: Configuration error — Field required" on startup

**Cause**: The `.env` file is missing or has missing required fields.

**Fix**:

```bash
cp .env.example .env
# Edit .env with your actual values
```

Required fields that have no defaults:
- `AUTH__URL`, `AUTH__CLIENT_ID`, `AUTH__CLIENT_SECRET`, `AUTH__USERNAME`, `AUTH__PASSWORD`
- `LOGIN__URL`, `LOGIN__BORDER_POST_ID`, `LOGIN__BOX_ID`, `LOGIN__PASSENGER_CONTROL_TYPE`
- `DOWNLOAD__URL`
- `DATABASE__DSN` (or `DATABASE__HOST` + `DATABASE__NAME` + `DATABASE__USERNAME` + `DATABASE__PASSWORD`)

---

### "No module named 'uvicorn'" or "No module named 'fastapi'"

**Cause**: The `server` extras were not installed.

**Fix**:

```bash
pip install -e ".[dev,server]"
```

---

### "Permission denied: .venv/Scripts/activate" (Windows)

**Cause**: PowerShell execution policy blocks scripts.

**Fix** (run PowerShell as Administrator once):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then re-run `.venv\Scripts\activate` in a normal PowerShell window.

---

### Tests fail with "docker not found" or testcontainers errors

**Cause**: Docker is not running (required for integration/acceptance tests).

**Fix**: Start Docker Desktop (Windows) or `sudo systemctl start docker` (Linux). Then run only
unit tests if Docker is not available:

```bash
pytest tests/unit/ -v
```

---

### Python 3.14 not found on Ubuntu

**Cause**: deadsnakes PPA not added or not refreshed.

**Fix**:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.14 python3.14-venv python3.14-dev
```

---

### "cryptography DeprecationWarning" in test output

This is expected. Some ICAO certificates have non-conformant ASN.1 (NULL signature parameters).
It is suppressed in `pytest` via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "ignore::cryptography.utils.CryptographyDeprecationWarning",
]
```

The warning does NOT appear during tests. If you see it when running the application directly,
it is harmless — the certificate is still parsed and stored correctly.
````

