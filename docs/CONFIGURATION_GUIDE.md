# Configuration Best Practices — Python vs Java

This document explains why cert-parser uses **pyproject.toml** and **.env** for configuration, and how they map to Java patterns your team is familiar with.

## Configuration Comparison

### Java Approach (Familiar to Your Team)

```
Java Project
├── pom.xml                    # Maven: dependencies, build config
├── src/main/resources/
│   ├── application.yaml       # Spring Boot config template
│   └── application-prod.yaml  # Production overrides
├── .env                       # Local development secrets
└── deployment.yaml            # K8s ConfigMap/Secret values
```

**How Spring Boot works**:
1. `pom.xml` defines dependencies (Maven Central)
2. `src/main/resources/application.yaml` is the default config
3. `application-{profile}.yaml` overrides per environment
4. Environment variables override YAML values
5. K8s ConfigMap/Secret inject env vars

### Python Approach (cert-parser)

```
Python Project
├── pyproject.toml             # Poetry/pip: dependencies + metadata
├── .env.example               # Config template (local dev)
├── .env                       # Local development values
└── k8s/configmap.yaml         # K8s ConfigMap/Secret values
```

**How cert-parser works**:
1. `pyproject.toml` defines dependencies (PyPI)
2. `pydantic-settings` loads from environment (with validation)
3. `.env.example` is the template (committed to Git)
4. `.env` is local development (NOT committed, ignored by .gitignore)
5. K8s ConfigMap/Secret inject env vars (same as Spring Boot)

## Why pyproject.toml > requirements.txt

| Feature | requirements.txt | pyproject.toml |
|---------|-----------------|----------------|
| **Dependency format** | `package==1.0.0` | Structured TOML with versions |
| **Optional extras** | Must use multiple files | `[project.optional-dependencies]` |
| **Build system** | Not specified | Standardized (PEP 517/518) |
| **Metadata** | Separate setup.py/setup.cfg | All in one file |
| **Git conflicts** | High (static list) | Low (structured) |
| **IDE support** | Basic | Excellent (modern Python tools) |
| **Reproducibility** | Good | Excellent (with pyproject.toml + lock file) |

### Example in cert-parser

```toml
[project]
name = "cert-parser"
version = "0.1.0"
dependencies = [
    "httpx[http2] >= 0.28.1",
    "asn1crypto >= 1.5.1",
    # ...
]

[project.optional-dependencies]
dev = [
    "pytest >= 8.3.0",
    "mypy >= 1.14.0",
    # ...
]
server = [
    "uvicorn[standard] >= 0.35.0",
    "fastapi >= 0.115.0",
]
```

Installation:
```bash
pip install -e ".[dev]"        # For development
pip install -e ".[server]"     # For production (Kubernetes)
pip install -e "."             # Core only
```

## Why .env > requirements.txt for Configuration

**requirements.txt** is for Python PACKAGE dependencies (from PyPI).
**.env** is for RUNTIME CONFIGURATION (credentials, URLs, etc.).

They serve completely different purposes!

### Configuration Hierarchy

```
1. Defaults (hardcoded in config.py)
   ↓
2. .env file (LOCAL DEVELOPMENT ONLY)
   ↓
3. Environment variables (set by K8s/shell)
   ↓
4. K8s ConfigMap/Secret (PRODUCTION)
```

In cert-parser:
```python
from pydantic_settings import BaseSettings

class AppSettings(BaseSettings):
    class Config:
        env_file = ".env"          # Load from .env if present
        env_file_encoding = "utf-8"

    auth_url: str                  # Loaded from AUTH_URL env var
    database_dsn: SecretStr        # Loaded from DATABASE_DSN (hidden from logs)
```

## Mapping to Java/Spring Boot Patterns

Your Java team should recognize this pattern:

### Java Spring Boot

```yaml
# application.yaml (default)
server:
  port: 8080
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/db
    password: ${DATABASE_PASSWORD}  # From env var

# In Dockerfile
ENV DATABASE_PASSWORD=${DB_PASS}

# In K8s deployment
env:
- name: DATABASE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: app-secrets
      key: db-password
```

### Python cert-parser (Equivalent)

```toml
# pyproject.toml (dependencies only)
[project]
dependencies = ["psycopg>=3.0.0"]
```

```python
# src/cert_parser/config.py (pydantic-settings)
class AppSettings(BaseSettings):
    database_dsn: SecretStr
    # Defaults to env var: DATABASE_DSN
```

```dockerfile
# Dockerfile (entrypoint)
ENV DATABASE_DSN=${DB_PASS}

# Or in K8s:
ENV DATABASE_DSN=postgresql://user:pass@postgres:5432/db
```

## K8s Integration (Same for Both)

### Java Spring Boot

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  SERVER_PORT: "8080"
  LOG_LEVEL: "INFO"
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
stringData:
  database-password: "secret123"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  containers:
  - env:
    - name: SERVER_PORT
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: SERVER_PORT
    - name: DATABASE_PASSWORD
      valueFrom:
        secretKeyRef:
          name: app-secrets
          key: database-password
```

### Python cert-parser (IDENTICAL K8s approach)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cert-parser-config
data:
  AUTH_URL: "https://..."
  LOG_LEVEL: "INFO"
---
apiVersion: v1
kind: Secret
metadata:
  name: cert-parser-secrets
stringData:
  DATABASE_DSN: "postgresql://..."
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cert-parser
spec:
  containers:
  - envFrom:
    - configMapRef:
        name: cert-parser-config
    env:
    - name: DATABASE_DSN
      valueFrom:
        secretKeyRef:
          name: cert-parser-secrets
          key: database-dsn
```

**The K8s manifests are IDENTICAL.** The only difference is how applications load configuration (Spring Boot uses properties/YAML, Python uses env vars).

## Local Development: .env.example vs application.yaml

### Java Team Pattern

```bash
# Copy template
cp src/main/resources/application.yaml application-local.yaml

# Edit local values
vi application-local.yaml

# Run with profile
./mvnw spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=local
```

### Python Pattern (Same concept)

```bash
# Copy template
cp .env.example .env

# Edit local values
vi .env

# Run (pydantic-settings auto-loads .env)
python -m cert_parser.main
```

**Same idea, different syntax.** Your team should find this pattern familiar!

## Summary: Why These Choices

| Choice | Why | Equivalent in Java |
|--------|-----|-------------------|
| **pyproject.toml** | Modern Python standard, better than requirements.txt | Like pom.xml |
| **.env** | Simple, fast, local dev only | Like application-local.yaml |
| **.env.example** | Template, committed to Git | Like application.yaml template |
| **pydantic-settings** | Type-safe, validates config, env var support | Like Spring Boot PropertySources |
| **K8s ConfigMap/Secret** | Standard K8s pattern for both Python and Java | Same in both ecosystems |

## Can You Use requirements.txt Instead?

**Yes, but not recommended:**

```bash
# Generate requirements.txt from pyproject.toml (one-time)
pip install pip-tools
pip-compile pyproject.toml -o requirements.txt

# But this loses metadata and optional dependencies
# You'd need: requirements-dev.txt, requirements-prod.txt, etc.
```

The tradeoff:
- ✅ Familiar to your Java team
- ❌ Loses structured metadata
- ❌ Duplicate version info (pyproject.toml + requirements.txt)
- ❌ Harder to maintain
- ❌ Not Python 3.14 best practices

**Recommendation**: Stick with `pyproject.toml`. Your team will adapt quickly once they see it's just a cleaner version of `pom.xml`.

## Quick Reference: Configuration File Locations

```
cert-parser/
├── pyproject.toml           # ← Dependencies (like pom.xml)
├── .env.example             # ← Config template (committed)
├── .env                     # ← Config values (local, not committed)
├── k8s/
│   ├── configmap.yaml       # ← K8s non-sensitive config
│   └── [secret handled externally]
└── src/
    └── cert_parser/
        └── config.py        # ← Pydantic model validates config
```

## Onboarding Your Java Team

1. **Show them**: "pyproject.toml is Python's pom.xml"
2. **Show them**: ".env is like application-local.yaml"
3. **Show them**: K8s ConfigMap/Secret usage is IDENTICAL
4. **Show them**: No difference in deployment or operations

The only difference is **developer experience** — Python is simpler (env vars instead of YAML parsing).

---

**Result**: Your team gets Python best practices while keeping the operational patterns they're comfortable with. Everyone wins!
