#!/bin/bash
# validate-deployment.sh — Validate cert-parser deployment on Kubernetes
# Usage: ./k8s/scripts/validate-deployment.sh [namespace] [timeout-seconds]

set -euo pipefail

NAMESPACE=${1:-"default"}
TIMEOUT=${2:-"300"}
LABEL="app=cert-parser"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Validating cert-parser deployment"
echo "Settings: namespace=${NAMESPACE}, timeout=${TIMEOUT}s"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if deployment exists
echo "[1] Checking deployment exists..."
if ! kubectl get deployment cert-parser -n "${NAMESPACE}" &>/dev/null; then
    echo "❌ Deployment not found in namespace '${NAMESPACE}'"
    echo "   Try: kubectl apply -f k8s/"
    exit 1
fi
echo "✓ Deployment found"
echo ""

# Check if ConfigMap exists
echo "[2] Checking ConfigMap..."
if ! kubectl get configmap cert-parser-config -n "${NAMESPACE}" &>/dev/null; then
    echo "❌ ConfigMap 'cert-parser-config' not found"
    exit 1
fi
echo "✓ ConfigMap found"
echo ""

# Check if Secret exists
echo "[3] Checking Secret..."
if ! kubectl get secret cert-parser-secrets -n "${NAMESPACE}" &>/dev/null; then
    echo "⚠ Secret 'cert-parser-secrets' not found – pods will fail to start"
    echo "  Create it with: kubectl create secret generic cert-parser-secrets ..."
    exit 1
fi
echo "✓ Secret found"
echo ""

# Wait for pods to be ready
echo "[4] Waiting for pods to be ready (timeout: ${TIMEOUT}s)..."
if ! kubectl wait --for=condition=ready pod -l "${LABEL}" -n "${NAMESPACE}" --timeout="${TIMEOUT}s" 2>/dev/null; then
    echo "❌ Pods did not become ready in time"
    echo ""
    echo "Pod status:"
    kubectl get pods -l "${LABEL}" -n "${NAMESPACE}"
    echo ""
    echo "Pod descriptions:"
    kubectl describe pods -l "${LABEL}" -n "${NAMESPACE}" | head -100
    echo ""
    echo "Recent logs:"
    kubectl logs -l "${LABEL}" -n "${NAMESPACE}" --tail=50
    exit 1
fi
echo "✓ Pods are ready"
echo ""

# Check service exists
echo "[5] Checking Service..."
if ! kubectl get svc cert-parser -n "${NAMESPACE}" &>/dev/null; then
    echo "❌ Service 'cert-parser' not found"
    exit 1
fi
echo "✓ Service found"
SERVICE_IP=$(kubectl get svc cert-parser -n "${NAMESPACE}" -o jsonpath='{.spec.clusterIP}')
echo "  ClusterIP: ${SERVICE_IP}"
echo ""

# Get pod name
echo "[6] Getting pod information..."
POD_NAME=$(kubectl get pods -l "${LABEL}" -n "${NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')
echo "  Pod: ${POD_NAME}"
echo ""

# Test health endpoint (via port-forward)
echo "[7] Testing /health endpoint..."
kubectl port-forward svc/cert-parser 8000:8000 -n "${NAMESPACE}" &
PF_PID=$!
sleep 1

if curl -s http://localhost:8000/health | jq . > /dev/null 2>&1; then
    echo "✓ /health endpoint responding"
    curl -s http://localhost:8000/health | jq .
else
    echo "❌ /health endpoint failed"
    kill $PF_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Test ready endpoint
echo "[8] Testing /ready endpoint..."
if curl -s http://localhost:8000/ready | jq . > /dev/null 2>&1; then
    echo "✓ /ready endpoint responding"
    curl -s http://localhost:8000/ready | jq .
else
    echo "❌ /ready endpoint failed"
    kill $PF_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Test info endpoint
echo "[9] Testing /info endpoint..."
if curl -s http://localhost:8000/info | jq . > /dev/null 2>&1; then
    echo "✓ /info endpoint responding"
    curl -s http://localhost:8000/info | jq .
else
    echo "❌ /info endpoint failed"
    kill $PF_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Kill port-forward
kill $PF_PID 2>/dev/null || true
sleep 1

# Check environment variables
echo "[10] Checking environment variables in pod..."
REQUIRED_VARS=(
    "AUTH_URL"
    "AUTH_CLIENT_ID"
    "AUTH_USERNAME"
    "LOGIN_URL"
    "LOGIN_BORDER_POST_ID"
    "DOWNLOAD_URL"
    "DATABASE_DSN"
    "SCHEDULER_INTERVAL_HOURS"
    "LOG_LEVEL"
)

for var in "${REQUIRED_VARS[@]}"; do
    if kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- env | grep -q "^${var}="; then
        echo "  ✓ ${var}"
    else
        echo "  ❌ ${var} not set"
        exit 1
    fi
done
echo ""

# Check logs for errors
echo "[11] Checking pod logs for errors..."
ERRORS=$(kubectl logs "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | grep -i error | wc -l)
if [ "${ERRORS}" -eq 0 ]; then
    echo "✓ No errors in logs"
else
    echo "⚠ Found ${ERRORS} error lines in logs"
    echo "  Recent logs:"
    kubectl logs "${POD_NAME}" -n "${NAMESPACE}" | tail -20
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ All validation checks passed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Deployment summary:"
kubectl get deployment,pods,svc -l "${LABEL}" -n "${NAMESPACE}"
echo ""
echo "Next steps:"
echo "  - Monitor logs: kubectl logs -l ${LABEL} -n ${NAMESPACE} -f"
echo "  - Get pod shell: kubectl exec -it ${POD_NAME} -n ${NAMESPACE} -- bash"
echo "  - Watch deployment: kubectl get pods -w -n ${NAMESPACE}"
echo ""
