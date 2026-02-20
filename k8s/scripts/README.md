# Kubernetes Helper Scripts

Quick-start scripts for building and deploying cert-parser.

## Scripts

### build-and-test.sh
Builds the Docker image and runs basic tests locally (no K8s needed).

```bash
./build-and-test.sh [version]

# Example
./build-and-test.sh v0.1.0
```

Tests performed:
- Image builds without errors
- Container starts and becomes healthy
- `/health` endpoint responds
- `/info` endpoint responds
- Container gracefully stops

### deploy-local.sh
Deploys to a local Kubernetes cluster (kind or minikube) with test configuration.

```bash
./deploy-local.sh [cluster-type]

# Examples
./deploy-local.sh kind          # For kind (default)
./deploy-local.sh minikube      # For minikube
```

What it does:
- Creates/starts local K8s cluster (kind or minikube)
- Builds Docker image
- Loads image into cluster
- Creates namespace
- Creates ConfigMap with test values (points to localhost for services)
- Creates Secret with test credentials
- Deploys cert-parser
- Waits for pods to be ready
- Shows access instructions

### validate-deployment.sh
Validates an existing cert-parser deployment is working correctly.

```bash
./validate-deployment.sh [namespace] [timeout]

# Examples
./validate-deployment.sh default
./validate-deployment.sh cert-parser 300
```

Validations performed:
- Deployment exists
- ConfigMap exists
- Secret exists
- Pods are ready
- Service is accessible
- Health endpoints respond (`/health`, `/ready`, `/info`)
- Environment variables are set correctly
- No errors in logs

## Quick Start (Local)

```bash
# 1. Build and test locally
./build-and-test.sh v0.1.0

# 2. Deploy to local K8s
./deploy-local.sh kind

# 3. Validate deployment
./validate-deployment.sh cert-parser

# 4. Monitor
kubectl port-forward svc/cert-parser 8000:8000 -n cert-parser &
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/info
```

## Production Deployment

See [../DEPLOYMENT.md](../DEPLOYMENT.md) for comprehensive production deployment guide.
