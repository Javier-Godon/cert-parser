#!/bin/bash
# deploy-local.sh — Deploy cert-parser to local K8s cluster (kind, minikube, etc.)
# Usage: ./k8s/scripts/deploy-local.sh [cluster-type]
# Example: ./k8s/scripts/deploy-local.sh kind
#          ./k8s/scripts/deploy-local.sh minikube

set -euo pipefail

CLUSTER_TYPE=${1:-"kind"}
NAMESPACE="cert-parser"
VERSION="v0.1.0"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Local K8s Deployment Script"
echo "Cluster type: ${CLUSTER_TYPE}"
echo "Namespace: ${NAMESPACE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check prerequisites
echo "[1] Checking prerequisites..."

if ! command -v kubectl &>/dev/null; then
    echo "❌ kubectl not found. Install kubectl first."
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo "❌ docker not found. Install docker first."
    exit 1
fi

case "${CLUSTER_TYPE}" in
  kind)
    if ! command -v kind &>/dev/null; then
      echo "❌ kind not found. Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/"
      exit 1
    fi
    echo "✓ kind found"
    ;;
  minikube)
    if ! command -v minikube &>/dev/null; then
      echo "❌ minikube not found. Install minikube: https://minikube.sigs.k8s.io/"
      exit 1
    fi
    echo "✓ minikube found"
    ;;
  *)
    echo "⚠ Unknown cluster type: ${CLUSTER_TYPE}"
    echo "   Continuing anyway (assuming cluster is running)..."
    ;;
esac

echo "✓ Prerequisites OK"
echo ""

# Create/start cluster
if [ "${CLUSTER_TYPE}" = "kind" ]; then
    echo "[2] Checking kind cluster..."
    if ! kind get clusters | grep -q "kind"; then
        echo "Creating kind cluster..."
        kind create cluster
    else
        echo "✓ kind cluster already exists"
    fi
    echo ""
elif [ "${CLUSTER_TYPE}" = "minikube" ]; then
    echo "[2] Checking minikube..."
    if ! minikube status | grep -q "Running"; then
        echo "Starting minikube..."
        minikube start
    else
        echo "✓ minikube is running"
    fi
    echo ""
fi

# Build image
echo "[3] Building cert-parser image..."
docker build \
  --progress=plain \
  -t "cert-parser:${VERSION}" \
  -t "cert-parser:latest" \
  .
echo "✓ Image built"
echo ""

# Load image into cluster (for kind)
if [ "${CLUSTER_TYPE}" = "kind" ]; then
    echo "[4] Loading image into kind cluster..."
    kind load docker-image "cert-parser:${VERSION}"
    echo "✓ Image loaded"
    echo ""
fi

# Create namespace
echo "[5] Creating namespace..."
kubectl create namespace "${NAMESPACE}" 2>/dev/null || echo "✓ Namespace already exists"
echo ""

# Create ConfigMap with test values
echo "[6] Creating ConfigMap..."
kubectl create configmap cert-parser-config \
  --from-literal=AUTH_URL='http://localhost:8001/token' \
  --from-literal=AUTH_CLIENT_ID='test-client' \
  --from-literal=AUTH_USERNAME='testuser' \
  --from-literal=LOGIN_URL='http://localhost:8002/auth/login' \
  --from-literal=LOGIN_BORDER_POST_ID='1' \
  --from-literal=LOGIN_BOX_ID='1' \
  --from-literal=LOGIN_PASSENGER_CONTROL_TYPE='1' \
  --from-literal=DOWNLOAD_URL='http://localhost:8003/download' \
  --from-literal=HTTP_TIMEOUT_SECONDS='60' \
  --from-literal=SCHEDULER_INTERVAL_HOURS='6' \
  --from-literal=RUN_ON_STARTUP='false' \
  --from-literal=LOG_LEVEL='INFO' \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "✓ ConfigMap created"
echo ""

# Create Secret with test values
echo "[7] Creating Secret..."
kubectl create secret generic cert-parser-secrets \
  --from-literal=auth-client-secret='test-secret' \
  --from-literal=auth-password='test-password' \
  --from-literal=database-dsn='postgresql://test:test@postgres:5432/test' \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "✓ Secret created"
echo ""

# Update deployment image
echo "[8] Patching deployment image..."
sed "s|IMAGE_PLACEHOLDER|cert-parser:${VERSION}|g" k8s/deployment.yaml | \
  kubectl apply -n "${NAMESPACE}" -f -
kubectl apply -f k8s/service.yaml -n "${NAMESPACE}"
echo "✓ Deployment applied"
echo ""

# Wait for pods
echo "[9] Waiting for pods to be ready (max 120s)..."
kubectl wait --for=condition=ready pod -l app=cert-parser -n "${NAMESPACE}" --timeout=120s || {
    echo "⚠ Pods not ready yet. Check status with:"
    echo "   kubectl get pods -n ${NAMESPACE}"
    echo "   kubectl describe pods -n ${NAMESPACE}"
   kubectl describe pods -n "${NAMESPACE}"
}
echo "✓ Pods are ready"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show deployment info
echo "Deployment info:"
kubectl get all -n "${NAMESPACE}"
echo ""

# Show how to access
echo "Access the application:"
echo "  kubectl port-forward svc/cert-parser 8000:8000 -n ${NAMESPACE}"
echo ""

echo "Monitoring:"
echo "  kubectl logs -f -l app=cert-parser -n ${NAMESPACE}"
echo "  kubectl get pods -w -n ${NAMESPACE}"
echo ""

echo "Cleanup:"
echo "  kubectl delete namespace ${NAMESPACE}"
if [ "${CLUSTER_TYPE}" = "kind" ]; then
    echo "  kind delete cluster"
elif [ "${CLUSTER_TYPE}" = "minikube" ]; then
    echo "  minikube delete"
fi
echo ""
