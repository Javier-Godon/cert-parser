# Production Deployment Architecture

Complete reference for cert-parser production setup on Kubernetes.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     KUBERNETES CLUSTER                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Namespace: cert-parser                                   │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │                                                          │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │ Deployment: cert-parser (replicas: 1)          │   │  │
│  │  ├─────────────────────────────────────────────────┤   │  │
│  │  │                                                 │   │  │
│  │  │  Pod (uvicorn + fastapi + apscheduler)        │   │  │
│  │  │  ├─ Port 8000: HTTP (health, ready, info)     │   │  │
│  │  │  ├─ Probes:                                    │   │  │
│  │  │  │  ├─ Startup (300s timeout)                 │   │  │
│  │  │  │  ├─ Liveness (30s interval)                │   │  │
│  │  │  │  └─ Readiness (10s interval)               │   │  │
│  │  │  └─ Env: ConfigMap + Secret                  │   │  │
│  │  │                                                 │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │                                                         │  │
│  │  ┌──────────────┐  ┌──────────────┐                   │  │
│  │  │ ConfigMap    │  │ Secret       │                   │  │
│  │  │ (public cfg) │  │ (sensitive)  │                   │  │
│  │  └──────────────┘  └──────────────┘                   │  │
│  │                                                         │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ Service (ClusterIP: port 8000)                  │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ External Resources (outside K8s)                         │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  ├─ PostgreSQL (5432)    ◄── stored certs + CRLs       │  │
│  │  ├─ OAuth2/OIDC (443)    ◄── auth_token               │  │
│  │  ├─ SFC Service (443)    ◄── sfc_token                │  │
│  │  └─ Download Service (443) ◄── .bin files            │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
cert_parser/
├── src/cert_parser/
│   ├── main.py                    # CLI entry point (local/testing)
│   ├── asgi.py                    # ASGI entry point (Uvicorn/K8s)
│   ├── config.py                  # Pydantic configuration
│   ├── pipeline.py                # ROP flat_map chain
│   ├── scheduler.py               # APScheduler setup
│   ├── domain/
│   │   ├── models.py              # Value objects (frozen dataclasses)
│   │   └── ports.py               # Protocol interfaces
│   └── adapters/
│       ├── http_client.py         # HTTP auth + download
│       ├── cms_parser.py          # CMS/PKCS#7 unwrapping
│       └── repository.py          # PostgreSQL persistence
├── Dockerfile                     # Multi-stage, production-ready
├── pyproject.toml                 # Dependencies (core + optional)
├── .env.example                   # Configuration template
└── k8s/                           # Kubernetes manifests
    ├── deployment.yaml            # Pod deployment (health checks, probes)
    ├── service.yaml               # Service + Ingress
    ├── configmap.yaml             # ConfigMap + Secret template
    ├── pdb-networkpolicy.yaml     # Security policies
    ├── DEPLOYMENT.md              # Complete deployment guide
    └── scripts/
        ├── build-and-test.sh      # Build image and run tests
        ├── deploy-local.sh        # Deploy to local K8s (kind/minikube)
        └── validate-deployment.sh # Verify deployment works
```

## Configuration Layers

### Layer 1: pyproject.toml Dependencies

Core dependencies:
```
railway-rop              # ROP framework
httpx                    # HTTP client (3-endpoint auth)
asn1crypto               # CMS/PKCS#7 unwrapping
cryptography             # X.509 certificate parsing
psycopg                  # PostgreSQL driver
APScheduler              # Scheduled background jobs
pydantic-settings        # Environment configuration
tenacity                 # Retry/backoff decorators
structlog                # Structured JSON logging
```

Optional dependencies (for production):
```
[server]
uvicorn                  # ASGI web server
fastapi                  # Web framework (health endpoints)
```

### Layer 2: Environment Variables (.env / ConfigMap)

**Non-sensitive** (in `ConfigMap`):
```
AUTH_URL                          # OIDC token endpoint
LOGIN_URL                         # SFC login endpoint
DOWNLOAD_URL                      # Certificate download endpoint
LOGIN_BORDER_POST_ID              # Border post config (int)
LOGIN_BOX_ID                      # Box ID (string)
LOGIN_PASSENGER_CONTROL_TYPE      # Type code (int)
HTTP_TIMEOUT_SECONDS              # HTTP request timeout
SCHEDULER_INTERVAL_HOURS          # Run schedule (hours)
RUN_ON_STARTUP                    # Run once on startup (bool)
LOG_LEVEL                         # DEBUG/INFO/WARNING/ERROR
```

**Sensitive** (in `Secret`, managed externally):
```
AUTH_CLIENT_ID                    # OAuth client ID
AUTH_CLIENT_SECRET                # OAuth client secret
AUTH_USERNAME                     # OIDC username
AUTH_PASSWORD                     # OIDC password
DATABASE_DSN                      # PostgreSQL connection string
```

### Layer 3: Kubernetes ConfigMap + Secret

**ConfigMap** (`cert-parser-config`):
- Created from `.env` example values
- Overridable via `kubectl set env`
- Mounted as environment variables in Pod
- Non-sensitive configuration only

**Secret** (`cert-parser-secrets`):
- Created independently (sealed-secrets, Vault, etc.)
- Referenced by Pod as environment variables
- Managed by external secrets management system
- **NEVER committed to Git**

## Authentication Flow

```
Step 1: Access Token (OpenID Connect)
─────────────────────────────────────
Client                          OIDC Provider
  │                                │
  ├─ POST /protocol/openid-connect/token
  │   grant_type=password           │
  │   client_id=...                 │
  │   client_secret=...             │
  │   username=...                  │
  │   password=...                  │
  ├────────────────────────────────▶│
  │                                 │
  │◀── 200 OK                       │
  │    {"access_token": "..."}      │
  │                                 │
  └─ Save: access_token


Step 2: SFC Token (Bearer + Login)
──────────────────────────────────
Client                          SFC Service
  │                                │
  ├─ POST /auth/v1/login           │
  │   Authorization: Bearer {access_token}
  │   {"borderPostId": 1,           │
  │    "boxId": "XX/99/X",          │
  │    "passengerControlType": 1}   │
  ├────────────────────────────────▶│
  │                                 │
  │◀── 200 OK                       │
  │    "simulated-sfc-token-xyz"    │
  │                                 │
  └─ Save: sfc_token


Step 3: Download (.bin file)
────────────────────────────
Client                          Download Service
  │                                │
  ├─ GET /certificates/csca        │
  │   Authorization: Bearer {access_token}
  │   x-sfc-authorization: Bearer {sfc_token}
  ├────────────────────────────────▶│
  │                                 │
  │◀── 200 OK                       │
  │    [binary .bin file]           │
  │                                 │
  └─ Process: parse → store
```

## Health Check Endpoints

| Endpoint | Purpose | K8s Probe | Response |
|----------|---------|-----------|----------|
| `/health` | Liveness (is scheduler alive?) | Liveness | 200 if scheduler running, 503 if error |
| `/ready` | Readiness (is startup complete?) | Readiness + Startup | 200 if ready, 202 if starting, 503 if error |
| `/info` | Debug info (scheduler status) | None | `{"status": "...", "scheduler_running": ...}` |

Probe Configuration (in deployment.yaml):
```yaml
startupProbe:      # Max 5 minutes for startup
  httpGet: /ready
  failureThreshold: 30
  periodSeconds: 10

livenessProbe:     # Check every 30s, fail after 3 misses
  httpGet: /health
  failureThreshold: 3
  periodSeconds: 30

readinessProbe:    # Check every 10s for readiness
  httpGet: /ready
  failureThreshold: 3
  periodSeconds: 10
```

## Docker Image

### Multi-Stage Build

**Stage 1: Builder**
- Base: `python:3.14-slim`
- Installs: build tools, git, libpq-dev
- Creates: Python venv, installs dependencies
- Produces: `/build/venv`

**Stage 2: Runtime**
- Base: `python:3.14-slim`
- Installs: libpq5 (runtime only), curl (health checks)
- Copy: `/build/venv` from stage 1
- User: `certparser:1000` (non-root)
- Size: ~350 MB

**Security Features**:
- Non-root user (UID 1000)
- Minimal image (slim base, no build tools)
- Health check built-in (curl)
- Read-only root filesystem (where possible)

### Build & Push

```bash
# Build locally
docker build -t cert-parser:v0.1.0 .

# Tag for registry
docker tag cert-parser:v0.1.0 your-registry.azurecr.io/cert-parser:v0.1.0

# Push
docker push your-registry.azurecr.io/cert-parser:v0.1.0

# Load into kind (for local testing)
kind load docker-image cert-parser:v0.1.0
```

## Kubernetes Manifests

### Deployment (deployment.yaml)

Key features:
- **1 replica** (scheduled batch job, not user-facing)
- **Rolling updates**: maxSurge=1, maxUnavailable=0 (graceful)
- **Graceful shutdown**: terminationGracePeriodSeconds=30 (Uvicorn drains)
- **Security context**: runAsNonRoot=true, fsGroup=1000
- **Health checks**: startup/liveness/readiness probes
- **Resource limits**: 512M memory / 500m CPU (adjust as needed)
- **ConfigMap/Secret mounting**: environment variables

### Service (service.yaml)

- **Type**: ClusterIP (internal only)
- **Port**: 8000 → container port 8000
- **Optional Ingress**: for external access to health endpoints

### ConfigMap/Secret (configmap.yaml)

ConfigMap: Non-sensitive configuration
Secret: Sensitive credentials (managed externally)

### Security (pdb-networkpolicy.yaml)

**PodDisruptionBudget** (PDB):
- minAvailable: 0 (allow evictions during maintenance)
- unhealthyPodEvictionPolicy: AlwaysAllow

**NetworkPolicy**:
- Egress: Allow DNS (53), HTTPS (443), PostgreSQL (5432)
- Ingress: Allow from monitoring namespace, local pods

## Deployment Workflow

### 1. Local Development

```bash
# Run locally without K8s
python -m cert_parser.main  # Uses APScheduler, no HTTP server

# Or with HTTP health endpoints
uvicorn cert_parser.asgi:app --reload
```

### 2. Local Testing (kind/minikube)

```bash
./k8s/scripts/build-and-test.sh v0.1.0       # Build + test image
./k8s/scripts/deploy-local.sh kind            # Deploy to kind
./k8s/scripts/validate-deployment.sh          # Verify
```

### 3. Production Deployment

```bash
# Push to registry
docker push your-registry/cert-parser:v0.1.0

# Create secrets (manually or via external system)
kubectl create secret generic cert-parser-secrets \
  --from-literal=auth-client-secret='...' \
  --from-literal=auth-password='...' \
  --from-literal=database-dsn='...'

# Deploy
kubectl apply -f k8s/configmap.yaml   # ConfigMap
kubectl apply -f k8s/deployment.yaml  # Deployment + Service
kubectl apply -f k8s/pdb-networkpolicy.yaml

# Verify
kubectl wait --for=condition=ready pod -l app=cert-parser --timeout=5m
kubectl logs -l app=cert-parser -f
```

## Monitoring & Observability

### Logs

Structured JSON logs to stdout (compatible with ELK, Splunk, Datadog):
```json
{
  "event": "pipeline.started",
  "timestamp": "2026-02-19T13:00:00Z",
  "execution_id": "abc123",
  "trigger": "scheduled"
}
```

Access via kubectl:
```bash
kubectl logs -l app=cert-parser -f
kubectl logs -l app=cert-parser --tail=100 | jq .
```

### Health Endpoints

```bash
# Port-forward
kubectl port-forward svc/cert-parser 8000:8000 &

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/info
```

### Metrics (Future)

Endpoints declared for Prometheus scraping:
```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

## Secrets Management

### Option 1: Sealed-Secrets (GitOps-friendly)

```bash
# Seal secrets (encrypt with cluster public key)
kubeseal -f secret.yaml -w sealed-secret.yaml

# Commit to Git (safe!)
git add sealed-secret.yaml

# Apply (controller decrypts automatically)
kubectl apply -f sealed-secret.yaml
```

### Option 2: HashiCorp Vault

Integrate with Vault agent for secret injection.

### Option 3: External Secrets Operator

Sync secrets from AWS Secrets Manager, Azure Key Vault, etc.

## Troubleshooting

### Pod CrashLoopBackOff

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
```

Common causes:
- Secret not created
- Database unreachable
- Log level too verbose

### Health Check Failing

```bash
kubectl port-forward svc/cert-parser 8000:8000 &
curl -v http://localhost:8000/health
```

Check logs for:
- Configuration errors
- Scheduler thread crashed
- Database connection failed

### Slow Startup

Startup probe has 5-minute window. Check logs:
```bash
kubectl logs -l app=cert-parser | grep -i "startup\|error"
```

CMS parsing can take time for large Master Lists (up to 1-2 minutes on first run).

## Production Checklist

- [ ] Docker image built and tested
- [ ] Pushed to production registry
- [ ] Secrets created (via sealed-secrets or Vault)
- [ ] ConfigMap values verified for production endpoints
- [ ] PostgreSQL access verified from K8s network
- [ ] Namespace created and NetworkPolicy applied
- [ ] PodDisruptionBudget configured
- [ ] Resource requests/limits set appropriately
- [ ] Health probes tested (`curl /health /ready /info`)
- [ ] Logs monitored and aggregated
- [ ] Monitoring/alerting configured (Prometheus)
- [ ] Backup/restore tested
- [ ] Runbook written for operators
- [ ] Graceful shutdown tested (SIGTERM → exit in <30s)
- [ ] Rollback procedure documented

## References

- [cert-parser README](../../README.md)
- [Kubernetes Deployment Guide](DEPLOYMENT.md)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/security/)
- [Uvicorn Documentation](https://www.uvicorn.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ConfigMap/Secret Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
