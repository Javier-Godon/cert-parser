# Dockerfile — Deep Dive

> This document explains every decision in the cert-parser `Dockerfile` so that any  
> developer, even one who has never written a Dockerfile before, can understand what  
> is happening and why.

---

## What Is a Dockerfile?

A **Dockerfile** is a script that describes how to build a **Docker image** — a portable,
self-contained snapshot of an application and everything it needs to run (Python, libraries,
your code). When you run a Docker image you get a **container**, which behaves the same way
on any machine that has Docker installed.

---

## What Does Our Dockerfile Do?

It creates a production-ready Docker image for cert-parser. The image:

- Runs **Python 3.14** inside a stripped-down Linux environment
- Installs only what the app needs at runtime (not build tools)
- Runs as a **non-root user** (security best practice)
- Exposes a web server on port 8000 with `/health` and `/ready` endpoints
- Is sized minimally (~350 MB) to reduce attack surface and deployment time

---

## Multi-Stage Build — The Key Pattern

Our Dockerfile uses a **multi-stage build**. Think of it as two separate boxes:

```
┌─────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│           STAGE 1: builder              │   │           STAGE 2: runtime               │
│                                         │   │                                          │
│  python:3.14-slim                       │   │  python:3.14-slim                        │
│  + git, build-essential, libpq-dev      │   │  + libpq5, curl                          │
│  + pip install everything               │   │  (no compiler, no git, no headers)       │
│  → produces: /app/venv                  │──▶│  + /app/venv  (copied from builder)      │
│                                         │   │  + /app/src   (our code)                 │
└─────────────────────────────────────────┘   └──────────────────────────────────────────┘
                  ↑ thrown away                              ↑ this is the shipped image
```

**Why?** Without this pattern, the final image would contain compilers, header files, and
`git` — tools needed only at build time. They add 200+ MB and unnecessary security risk.
With multi-stage, ONLY the compiled result (`/app/venv`) is copied into the final image.

---

## Stage 1: Builder

```dockerfile
FROM python:3.14-slim AS builder
```

**`FROM python:3.14-slim`** — starts from the official Python 3.14 image.
`slim` means no documentation, no unnecessary binaries — a smaller base.

**`AS builder`** — gives this stage a name so stage 2 can reference it.

```dockerfile
WORKDIR /build
```

Sets the working directory inside the builder container. All subsequent commands run here.

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

Installs **build-time** dependencies:

| Package | Why |
|---------|-----|
| `git` | Required by `hatchling` (our build backend) to read version metadata from the git repo |
| `build-essential` | C compiler (`gcc`) needed to compile Python packages with C extensions |
| `libpq-dev` | PostgreSQL client headers required to compile `psycopg[binary]` |

`--no-install-recommends` avoids pulling in optional packages.
`rm -rf /var/lib/apt/lists/*` clears the apt package cache to keep layer size small.

```dockerfile
COPY pyproject.toml pyproject.toml
COPY README.md README.md
COPY python_framework/ python_framework/
COPY src/ src/
```

Copies the source code into the builder. `README.md` is required because `hatchling`
(our build system) reads it for the package description metadata.

```dockerfile
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
```

Creates a **virtual environment** at `/app/venv`. This is critically placed at `/app/venv`
(not `/build/venv`) because the runtime stage will use this exact path.

**Why this matters**: pip writes shebang lines (`#!/app/venv/bin/python`) into entry-point
scripts. If the path changed between build and runtime, those scripts would be broken.

```dockerfile
RUN pip install --upgrade pip setuptools wheel && \
    pip install "./python_framework" && \
    pip install ".[server]"
```

Installs dependencies in the correct order:
1. Upgrade `pip` / `setuptools` / `wheel` to the latest stable versions
2. Install our local `railway-rop` framework first (cert-parser depends on it)
3. Install cert-parser with the `[server]` extra (adds `uvicorn` and `fastapi`)

> **Note**: We do NOT install `[dev]` extras (pytest, mypy, ruff) — those are for development
> only and do not belong in a production image.

---

## Stage 2: Runtime

```dockerfile
FROM python:3.14-slim
```

A fresh, clean `python:3.14-slim` — no build tools, no compiler, no intermediate layers.

```dockerfile
LABEL maintainer="BlueSolution"
LABEL description="cert-parser: ICAO Master List certificate parser for Kubernetes"
```

Metadata attached to the image (visible in `docker inspect`).

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

Installs ONLY runtime packages:

| Package | Why |
|---------|-----|
| `libpq5` | PostgreSQL client library needed to connect to PostgreSQL at runtime |
| `curl` | Used by the Docker health check (`HEALTHCHECK CMD curl -f http://localhost:8000/health`) |

No compiler, no headers, no `git` — production machines don't need those.

```dockerfile
RUN useradd -m -u 1000 -s /bin/bash certparser
```

Creates a **non-root user** named `certparser` with UID 1000.

**Why?** Running as `root` inside a container is dangerous: if an attacker exploits a
vulnerability in the app, they would have root access inside the container, making container
escape and host compromise much easier. Running as an unprivileged user limits the blast radius.

```dockerfile
COPY --from=builder --chown=certparser:certparser /app/venv /app/venv
```

Copies the entire virtual environment from the builder stage. `--from=builder` references
stage 1 by name. `--chown=certparser:certparser` sets the file owner so the non-root user
can read the installed packages.

```dockerfile
COPY --chown=certparser:certparser src/ /app/src/
```

Copies the application source code. Only `src/` — not tests, not scripts, not fixtures.

```dockerfile
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src
```

| Variable | Value | Meaning |
|----------|-------|---------|
| `PATH` | includes `/app/venv/bin` | Python and all installed binaries use the venv |
| `PYTHONUNBUFFERED` | `1` | Logs appear immediately in `docker logs` (no buffering) |
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevents writing `.pyc` files (not needed in containers) |
| `PYTHONPATH` | `/app/src` | Python can import `cert_parser` without the package being installed |

```dockerfile
USER certparser
```

Switches to the non-root user for all subsequent commands — including the running process.
Everything from this line on runs as `certparser`, not `root`.

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

Docker (and Kubernetes) will call this command every 30 seconds. If it fails 3 times,
the container is marked **unhealthy**.

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `--interval=30s` | Every 30 seconds | How often to check |
| `--timeout=5s` | 5 seconds | The curl must complete within 5 seconds |
| `--start-period=10s` | 10 seconds | Wait 10s before the first check (app boot time) |
| `--retries=3` | 3 failures | Mark unhealthy only after 3 consecutive failures |

```dockerfile
EXPOSE 8000
```

Documents that the container listens on port 8000. (Does not actually open the port — that
happens with `docker run -p 8000:8000` or via Kubernetes Service.)

```dockerfile
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["cert_parser.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**`ENTRYPOINT`** — the command that always runs. We use `python -m uvicorn` (module form)
instead of the `uvicorn` entry-point script to avoid any shebang resolution issues.

**`CMD`** — arguments passed to the entrypoint. Together they run:

```
python -m uvicorn cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1
```

- `cert_parser.asgi:app` — tells uvicorn to load the `app` object from `cert_parser/asgi.py`
- `--host 0.0.0.0` — listen on all network interfaces (required inside a container)
- `--port 8000` — our chosen port
- `--workers 1` — single worker process (APScheduler runs inside and must not be forked)

> **Why `--workers 1`?** APScheduler runs in a background thread. If we forked multiple
> worker processes, each process would have its own scheduler instance and the pipeline
> would run multiple times simultaneously. One worker keeps it single-threaded.

---

## Layer Caching

Docker builds are incremental. Each `COPY` and `RUN` creates a cached layer:

```
Layer 1: apt-get install (rarely changes)    → cached almost always
Layer 2: COPY pyproject.toml                 → invalidated when deps change
Layer 3: pip install                         → reinstalled only when deps change
Layer 4: COPY src/                           → invalidated on every code change
```

This order means editing Python code (frequent) does NOT re-run `pip install` (slow).
Only changing `pyproject.toml` triggers a full re-install.

---

## Building and Running Locally

```bash
# Build the image
docker build -t cert-parser:local .

# Run it (with env vars from .env file)
docker run --env-file .env -p 8000:8000 cert-parser:local

# Check health
curl http://localhost:8000/health

# View logs
docker logs -f <container-id>

# Run without scheduler (one-shot for testing)
docker run --env-file .env cert-parser:local \
    cert_parser.asgi:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## Security Checklist

| Control | Implementation |
|---------|---------------|
| Non-root user | `USER certparser` (UID 1000) |
| Minimal installed packages | Only `libpq5` and `curl` at runtime |
| No secrets in the image | All credentials via env vars at runtime |
| No dev tools in production | `[dev]` extras never installed |
| Health endpoint | `/health` for container orchestration |
| Small base image | `python:3.14-slim` not `python:3.14` |

---

## Related Documents

- [Technology Stack & Tooling](tooling-for-newcomers.md) — what each tool is
- [ASGI & Web Server](tooling-for-newcomers.md#asgi-fastapi-and-uvicorn) — FastAPI + Uvicorn explained
- [Kubernetes Deployment](../ARCHITECTURE_K8S.md) — how the image is deployed in production
- [Configuration Guide](configuration.md) — which environment variables to set
