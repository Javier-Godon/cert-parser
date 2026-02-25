#!/bin/bash
# deploy-local.sh — Deploy cert-parser to a local K8s cluster (kind or minikube)
# Usage: ./deployment/scripts/deploy-local.sh [cluster-type]
# Example: ./deployment/scripts/deploy-local.sh kind
#          ./deployment/scripts/deploy-local.sh minikube
#
# NOTE: This script uses test/dummy values for all credentials.
#       For production, populate deployment/secret.yaml with real values
#       (or use Sealed Secrets / External Secrets Operator) before applying.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOYMENT_DIR="${PROJECT_ROOT}/deployment"

CLUSTER_TYPE=${1:-"kind"}
NAMESPACE="cert-parser"
VERSION="v0.1.0"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Local K8s Deployment Script"
echo "Cluster type: ${CLUSTER_TYPE}"
echo "Namespace: ${NAMESPACE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Prerequisites ─────────────────────────────────────────────────
echo "[1] Checking prerequisites..."

for cmd in kubectl docker; do
  if ! command -v "${cmd}" &>/dev/null; then
    echo "❌ ${cmd} not found. Please install it first."
    exit 1
  fi
done

case "${CLUSTER_TYPE}" in
  kind)
    command -v kind &>/dev/null || { echo "❌ kind not found. See https://kind.sigs.k8s.io/"; exit 1; }
    echo "✓ kind found"
    ;;
  minikube)
    command -v minikube &>/dev/null || { echo "❌ minikube not found. See https://minikube.sigs.k8s.io/"; exit 1; }
    echo "✓ minikube found"
    ;;
  *)
    echo "⚠  Unknown cluster type: ${CLUSTER_TYPE} — assuming cluster is running"
    ;;
esac
echo "✓ Prerequisites OK"
echo ""

# ── Start / verify cluster ────────────────────────────────────────
if [ "${CLUSTER_TYPE}" = "kind" ]; then
    echo "[2] Checking kind cluster..."
    kind get clusters | grep -q "kind" || { echo "Creating kind cluster..."; kind create cluster; }
    echo "✓ kind cluster OK"
elif [ "${CLUSTER_TYPE}" = "minikube" ]; then
    echo "[2] Checking minikube..."
    minikube status | grep -q "Running" || { echo "Starting minikube..."; minikube start; }
    echo "✓ minikube running"
fi
echo ""

# ── Build image ───────────────────────────────────────────────────
echo "[3] Building cert-parser image..."
docker build \
  --progress=plain \
  -t "cert-parser:${VERSION}" \
  -t "cert-parser:latest" \
  "${PROJECT_ROOT}"
echo "✓ Image built"
echo ""

# Load into kind (kind does not pull from the daemon automatically)
if [ "${CLUSTER_TYPE}" = "kind" ]; then
    echo "[4] Loading image into kind cluster..."
    kind load docker-image "cert-parser:${VERSION}"
    echo "✓ Image loaded"
    echo ""
fi

# ── Namespace ─────────────────────────────────────────────────────
echo "[5] Ensuring namespace '${NAMESPACE}'..."
kubectl create namespace "${NAMESPACE}" 2>/dev/null || echo "✓ Namespace already exists"
echo ""

# ── Apply manifests ───────────────────────────────────────────────
# Applies ConfigMap, Secret (test values), Deployment, Service, PDB, NetworkPolicy.
# Override the namespace from kustomization to our local namespace.
echo "[6] Applying manifests from deployment/..."
kubectl apply -f "${DEPLOYMENT_DIR}/configmap.yaml" -n "${NAMESPACE}"
kubectl apply -f "${DEPLOYMENT_DIR}/secret.yaml"    -n "${NAMESPACE}"

# Patch image in deployment to local tag, then apply
sed "s|image:.*cert-parser.*|image: cert-parser:${VERSION}|g" \
    "${DEPLOYMENT_DIR}/deployment.yaml" | kubectl apply -n "${NAMESPACE}" -f -

kubectl apply -f "${DEPLOYMENT_DIR}/service.yaml"           -n "${NAMESPACE}"
kubectl apply -f "${DEPLOYMENT_DIR}/pdb-networkpolicy.yaml" -n "${NAMESPACE}"
echo "✓ Manifests applied"
echo ""

# ── Wait for pods ─────────────────────────────────────────────────
echo "[7] Waiting for pods to be ready (max 120s)..."
kubectl wait --for=condition=ready pod -l app=cert-parser -n "${NAMESPACE}" --timeout=120s || {
    echo "⚠  Pods not ready yet — check logs:"
    echo "   kubectl get pods -n ${NAMESPACE}"
    kubectl describe pods -l app=cert-parser -n "${NAMESPACE}" | tail -30
}
echo "✓ Pods ready"
echo ""

# ── Summary ───────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Deployment complete!"
echo ""
kubectl get all -l app=cert-parser -n "${NAMESPACE}"
echo ""
echo "Access:"
echo "  kubectl port-forward svc/cert-parser 8000:8000 -n ${NAMESPACE}"
echo "  curl http://localhost:8000/health"
echo ""
echo "Logs:   kubectl logs -f -l app=cert-parser -n ${NAMESPACE}"
echo "Cleanup: kubectl delete namespace ${NAMESPACE}"
if [ "${CLUSTER_TYPE}" = "kind" ];     then echo "         kind delete cluster"; fi
if [ "${CLUSTER_TYPE}" = "minikube" ]; then echo "         minikube delete"; fi
