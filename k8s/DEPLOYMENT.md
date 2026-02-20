# Kubernetes Deployment Guide — cert-parser

This guide covers production deployment of cert-parser on Kubernetes with proper configuration management, secrets handling, and monitoring.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Building & Pushing Docker Image](#building--pushing-docker-image)
4. [Secrets Management](#secrets-management)
5. [Deploying to Kubernetes](#deploying-to-kubernetes)
6. [Verifying Deployment](#verifying-deployment)
7. [Monitoring & Observability](#monitoring--observability)
8. [Troubleshooting](#troubleshooting)
9. [Cleanup](#cleanup)

## Overview

cert-parser runs as a **Uvicorn + FastAPI** web service in Kubernetes:

- **Docker image**: Multi-stage build with Python 3.14, ~350 MB
- **Deployment model**: Rolling updates, 1 replica (batch job, not user-facing API)
- **Configuration**: ConfigMap (non-sensitive) + Secret (sensitive)
- **Health checks**: 
  - `/health` — liveness (scheduler running)
  - `/ready` — readiness (scheduler started)
  - `/info` — debug information
- **Graceful shutdown**: SIGTERM → Uvicorn drains + exits

### Architecture

```
┌─────────────────┐
│  Kubernetes     │
│  Pod            │
├─────────────────┤
│ Uvicorn (port   │ ◄─ Exposed via Service:8000
│   8000)         │
│  ├─ /health     │
│  ├─ /ready      │
│  └─ /info       │
└────────┬────────┘
         │
         └─► APScheduler Thread
             └─► Pipeline: AuthToken → SFC → Download → Parse → Store
  ```

## Prerequisites

- Docker installed locally
- kubectl configured and access to a K8s cluster
- Container registry (Docker Hub, ECR, GCR, Harbor, etc.)
- PostgreSQL accessible from K8s cluster
- Secrets management tool (sealed-secrets, kustomize, Helm, etc.) — recommended for prod

## Building & Pushing Docker Image

### 1. Build locally

```bash
cd /home/javier/javier/workspaces/cert_parser

# Build with tag
docker build -t cert-parser:v0.1.0 .

# Verify image
docker images | grep cert-parser
docker run --rm cert-parser:v0.1.0 echo "Image works"
```

### 2. Tag for your registry

```bash
# Replace with your registry (Docker Hub, ECR, GCR, etc.)
REGISTRY=your-registry.azurecr.io  # Example: Azure Container Registry
IMAGE_NAME=cert-parser
VERSION=v0.1.0

docker tag cert-parser:${VERSION} ${REGISTRY}/${IMAGE_NAME}:${VERSION}
docker tag cert-parser:${VERSION} ${REGISTRY}/${IMAGE_NAME}:latest
```

### 3. Push to registry

```bash
# Login (varies by registry)
az acr login --name your-registry  # For Azure
# or
docker login your-registry.azurecr.io

# Push
docker push ${REGISTRY}/${IMAGE_NAME}:${VERSION}
docker push ${REGISTRY}/${IMAGE_NAME}:latest
```

## Secrets Management

### Option 1: Manual Secret Creation (dev/test)

```bash
# Create secret from sensitive values (NOT RECOMMENDED FOR PRODUCTION)
kubectl create namespace cert-parser  # Optional: create namespace
kubectl create secret generic cert-parser-secrets \
  --from-literal=auth-client-secret='your-real-client-secret' \
  --from-literal=auth-password='your-real-password' \
  --from-literal=database-dsn='postgresql://user:pwd@postgres:5432/db' \
  -n default
```

### Option 2: Using sealed-secrets (recommended for GitOps)

```bash
# Install sealed-secrets controller (one-time)
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Create a secret YAML locally
cat > secret.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: cert-parser-secrets
type: Opaque
data:
  auth-client-secret: $(echo -n 'your-real-secret' | base64)
  auth-password: $(echo -n 'your-real-password' | base64)
  database-dsn: $(echo -n 'postgresql://user:pwd@postgres:5432/db' | base64)
EOF

# Seal the secret (encrypt with cluster's public key)
kubeseal -f secret.yaml -w sealed-secret.yaml

# Commit sealed-secret.yaml to Git (safe, encrypted)
# Apply when needed
kubectl apply -f sealed-secret.yaml
```

### Option 3: Using Helm Secrets or Kustomize

See `.helmignore` or `kustomization.yaml` examples below.

## Deploying to Kubernetes

### Step 1: Update manifests with your values

Edit `k8s/configmap.yaml`:
```bash
# Edit these values
AUTH_URL=https://your-keycloak/...
LOGIN_URL=https://your-api/...
DOWNLOAD_URL=https://your-api/...
DATABASE_DSN=postgresql://...  # In Secret, not ConfigMap
```

Edit `k8s/service.yaml`:
```bash
# Update hostname in Ingress
- host: cert-parser.your-domain.com
```

### Step 2: Create namespace (optional)

```bash
kubectl create namespace cert-parser
```

### Step 3: Apply manifests

```bash
# Create ConfigMap and Secret
kubectl apply -f k8s/configmap.yaml

# Create Deployment and Service
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Apply security policies
kubectl apply -f k8s/pdb-networkpolicy.yaml
```

### Step 4: Verify deployment

```bash
# Check pods
kubectl get pods -l app=cert-parser -w

# Wait for ready
kubectl wait --for=condition=ready pod -l app=cert-parser --timeout=5m
```

## Verifying Deployment

### Check pod status

```bash
# List pods
kubectl get pods -l app=cert-parser
kubectl describe pod -l app=cert-parser

# View logs
kubectl logs -l app=cert-parser -f
kubectl logs -l app=cert-parser --tail=100
```

### Test health endpoints

```bash
# Port-forward to localhost (for testing from dev machine)
kubectl port-forward svc/cert-parser 8000:8000 &

# Test health check
curl http://localhost:8000/health

# Test readiness
curl http://localhost:8000/ready

# Get info
curl http://localhost:8000/info

# Kill port-forward
kill %1
```

### Exec into pod (for debugging)

```bash
# Get shell access
kubectl exec -it <pod-name> -- /bin/bash

# Check environment variables
env | grep AUTH_
env | grep LOGIN_
env | grep DOWNLOAD_

# Check if scheduler is running
ps aux | grep scheduler
```

## Monitoring & Observability

### 1. Structured JSON Logs

All logs are structured JSON:
```bash
kubectl logs -l app=cert-parser --tail=50 | jq .
```

### 2. Prometheus Metrics (future)

The `/metrics` endpoint is declared in deployment.yaml for Prometheus scraping:
```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8000"
prometheus.io/path: "/metrics"
```

Add Prometheus ServiceMonitor:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: cert-parser
spec:
  selector:
    matchLabels:
      app: cert-parser
  endpoints:
  - port: http
    interval: 30s
```

### 3. Alerting Rules

Create PrometheusRule for alerting:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cert-parser-alerts
spec:
  groups:
  - name: cert-parser
    rules:
    - alert: CertParserUnhealthy
      expr: kube_pod_status_ready{pod=~"cert-parser.*"} == 0
      for: 5m
      annotations:
        summary: "cert-parser pod is unhealthy"
        
    - alert: CertParserSchedulerNotRunning
      expr: up{job="cert-parser"} == 0
      for: 2m
      annotations:
        summary: "cert-parser scheduler is not running"
```

## Troubleshooting

### Pod won't start

```bash
# Check events
kubectl describe pod -l app=cert-parser

# Check logs
kubectl logs -l app=cert-parser --previous

# Common causes:
# - ConfigMap/Secret not created
# - Image not found in registry
# - Insufficient resources
# - Database unreachable
```

### Pod crashes after startup

```bash
# Check logs for errors
kubectl logs -l app=cert-parser

# Check resource limits
kubectl get pod -l app=cert-parser -o yaml | grep -A5 resources:

# Check environment variables
kubectl exec <pod-name> -- env | grep -E 'AUTH_|LOGIN_|DOWNLOAD_|DATABASE_'
```

### Health check failing

```bash
# Port-forward and test manually
kubectl port-forward svc/cert-parser 8000:8000 &
curl -v http://localhost:8000/health
curl -v http://localhost:8000/ready

# Check if scheduler thread is running
kubectl exec <pod-name> -- ps aux | grep -i scheduler

# Check logs for configuration errors
kubectl logs <pod-name> | grep -i error
```

### Scheduler not running scheduled tasks

```bash
# Check scheduler configuration
kubectl exec <pod-name> -- env | grep SCHEDULER_

# Check interval (should be in hours)
kubectl exec <pod-name> -- env | grep SCHEDULER_INTERVAL_HOURS

# Manually trigger a run by restarting:
kubectl delete pod -l app=cert-parser
# Pod will be recreated and (if RUN_ON_STARTUP=true) run once immediately
```

## Cleanup

### Delete deployment

```bash
# Delete all resources
kubectl delete -f k8s/

# Delete namespace (if created separately)
kubectl delete namespace cert-parser
```

### Remove Secret from cluster

```bash
kubectl delete secret cert-parser-secrets
kubectl delete configmap cert-parser-config
```

## Advanced: GitOps with ArgoCD

### Create ArgoCD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cert-parser
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/yourorg/cert-parser
    targetRevision: main
    path: k8s/
  destination:
    server: https://kubernetes.default.svc
    namespace: cert-parser
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

### Helm Chart (optional alternative to kubectl)

```bash
# Create Helm chart structure
helm create cert-parser-chart

# Deploy via Helm
helm install cert-parser ./cert-parser-chart -n cert-parser --create-namespace \
  -f values-prod.yaml \
  --set image.tag=v0.1.0
```

## Production Checklist

- [ ] Docker image built and pushed to registry
- [ ] SecureString/sealed-secrets created for sensitive values
- [ ] ConfigMap updated with correct endpoints
- [ ] Namespace created and isolated (NetworkPolicy applied)
- [ ] Deployment replicas >= 1
- [ ] Resource requests/limits set appropriately
- [ ] Health checks tested (`/health`, `/ready`)
- [ ] Logs verified (structured JSON)
- [ ] Pod disruption budget configured
- [ ] Monitoring/alerting configured (Prometheus)
- [ ] Runbook documented for operations team
- [ ] Graceful shutdown tested (SIGTERM → exit)
- [ ] Database backup tested
- [ ] Backup/restore procedure documented

## Support & Links

- cert-parser README: [../../README.md](../../README.md)
- Docker best practices: https://docs.docker.com/develop/dev-best-practices/
- K8s best practices: https://kubernetes.io/docs/concepts/security/
- Uvicorn documentation: https://www.uvicorn.org/
- FastAPI documentation: https://fastapi.tiangolo.com/
