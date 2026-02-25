#!/bin/bash
# validate-deployment.sh — Validate a running cert-parser deployment
# Usage: ./deployment/scripts/validate-deployment.sh [namespace] [timeout-seconds]

set -euo pipefail

NAMESPACE=${1:-"default"}
TIMEOUT=${2:-"300"}
LABEL="app=cert-parser"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Validating cert-parser deployment"
echo "  namespace : ${NAMESPACE}"
echo "  timeout   : ${TIMEOUT}s"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Resource existence ────────────────────────────────────────────
echo "[1] Checking Deployment..."
kubectl get deployment cert-parser -n "${NAMESPACE}" &>/dev/null || {
    echo "❌ Deployment not found in namespace '${NAMESPACE}'"
    echo "   Run: kubectl apply -f deployment/ -n ${NAMESPACE}"
    exit 1
}
echo "✓ Deployment found"

echo "[2] Checking ConfigMap..."
kubectl get configmap cert-parser-config -n "${NAMESPACE}" &>/dev/null || {
    echo "❌ ConfigMap 'cert-parser-config' not found"
    exit 1
}
echo "✓ ConfigMap found"

echo "[3] Checking Secret..."
kubectl get secret cert-parser-secrets -n "${NAMESPACE}" &>/dev/null || {
    echo "⚠  Secret 'cert-parser-secrets' not found — pods will fail to start"
    exit 1
}
echo "✓ Secret found"
echo ""

# ── Pod readiness ─────────────────────────────────────────────────
echo "[4] Waiting for pods to be ready (timeout: ${TIMEOUT}s)..."
kubectl wait --for=condition=ready pod -l "${LABEL}" -n "${NAMESPACE}" --timeout="${TIMEOUT}s" 2>/dev/null || {
    echo "❌ Pods did not become ready in time"
    kubectl get pods -l "${LABEL}" -n "${NAMESPACE}"
    echo ""
    kubectl describe pods -l "${LABEL}" -n "${NAMESPACE}" | head -60
    echo ""
    kubectl logs -l "${LABEL}" -n "${NAMESPACE}" --tail=30
    exit 1
}
echo "✓ Pods are ready"
echo ""

# ── Service ───────────────────────────────────────────────────────
echo "[5] Checking Service..."
kubectl get svc cert-parser -n "${NAMESPACE}" &>/dev/null || {
    echo "❌ Service 'cert-parser' not found"
    exit 1
}
CLUSTER_IP=$(kubectl get svc cert-parser -n "${NAMESPACE}" -o jsonpath='{.spec.clusterIP}')
echo "✓ Service found (ClusterIP: ${CLUSTER_IP})"
echo ""

POD_NAME=$(kubectl get pods -l "${LABEL}" -n "${NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')
echo "  Pod: ${POD_NAME}"
echo ""

# ── HTTP endpoints (via port-forward) ────────────────────────────
echo "[6] Starting port-forward for endpoint tests..."
kubectl port-forward svc/cert-parser 8000:8000 -n "${NAMESPACE}" &
PF_PID=$!
sleep 2

_check_endpoint() {
    local path="$1"
    if curl -sf "http://localhost:8000${path}" | python3 -m json.tool > /dev/null 2>&1; then
        echo "✓ ${path} OK"
        curl -sf "http://localhost:8000${path}" | python3 -m json.tool
    else
        echo "❌ ${path} failed"
        kill "${PF_PID}" 2>/dev/null || true
        exit 1
    fi
    echo ""
}

echo "[7] Testing /health..."
_check_endpoint "/health"

echo "[8] Testing /ready..."
_check_endpoint "/ready"

echo "[9] Testing /info..."
_check_endpoint "/info"

kill "${PF_PID}" 2>/dev/null || true
sleep 1

# ── Env vars (pydantic-settings __ delimiter) ─────────────────────
# Checks the env vars as they actually appear inside the pod.
echo "[10] Checking required environment variables in pod..."
REQUIRED_VARS=(
    "AUTH__URL"
    "AUTH__CLIENT_ID"
    "AUTH__USERNAME"
    "AUTH__CLIENT_SECRET"
    "AUTH__PASSWORD"
    "LOGIN__URL"
    "LOGIN__BORDER_POST_ID"
    "DOWNLOAD__URL"
    "DATABASE__PASSWORD"
    "SCHEDULER__CRON"
    "LOG_LEVEL"
)

for var in "${REQUIRED_VARS[@]}"; do
    if kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- env | grep -q "^${var}="; then
        echo "  ✓ ${var}"
    else
        echo "  ❌ ${var} not set — check configmap.yaml / secret.yaml"
    fi
done
echo ""

# ── Log scan ──────────────────────────────────────────────────────
echo "[11] Scanning pod logs for errors..."
ERROR_COUNT=$(kubectl logs "${POD_NAME}" -n "${NAMESPACE}" 2>/dev/null | grep -ci '"level":"error"\|ERROR\|Exception' || true)
if [ "${ERROR_COUNT}" -eq 0 ]; then
    echo "✓ No errors in logs"
else
    echo "⚠  Found ${ERROR_COUNT} error line(s) in logs:"
    kubectl logs "${POD_NAME}" -n "${NAMESPACE}" | tail -20
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ All validation checks passed!"
echo ""
kubectl get deployment,pods,svc -l "${LABEL}" -n "${NAMESPACE}"
echo ""
echo "Useful commands:"
echo "  Logs:     kubectl logs -l ${LABEL} -n ${NAMESPACE} -f"
echo "  Shell:    kubectl exec -it ${POD_NAME} -n ${NAMESPACE} -- bash"
echo "  Watch:    kubectl get pods -w -n ${NAMESPACE}"
echo "  Trigger:  kubectl port-forward svc/cert-parser 8000:8000 -n ${NAMESPACE}"
echo "            curl -X POST http://localhost:8000/trigger"
