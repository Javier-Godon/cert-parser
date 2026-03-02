#!/bin/bash
# deploy.sh — Deploy cert-parser to Kubernetes.
#
# What this script does:
#   1. Generates deployment/ghcr-secret.yaml by copying the ghcr-secret from
#      the prt-simulator namespace (Kubernetes secrets are namespace-scoped and
#      cannot be shared; the file is gitignored so it must be generated at deploy time).
#   2. Applies all manifests via: kubectl apply -k deployment/
#   3. Waits for the rollout to complete and prints useful follow-up commands.
#
# Prerequisites:
#   - kubectl configured and pointing at the target cluster
#   - ghcr-secret must already exist in the prt-simulator namespace
#   - cert-parser image already built and pushed to GHCR via the Dagger pipeline:
#       cd dagger_go && ./run.sh
#   - Set the real DATABASE__PASSWORD in deployment/secret.yaml before deploying
#
# Usage:
#   ./deployment/deploy.sh              # full deploy
#   ./deployment/deploy.sh --dry-run    # preview changes (server-side dry run)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="cert-parser"
DRY_RUN=""

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run=server"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "cert-parser — Kubernetes deployment"
[[ -n "${DRY_RUN}" ]] && echo "(dry-run mode)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Step 1: generate ghcr-secret.yaml ────────────────────────────────────────
# ghcr-secret.yaml is gitignored (contains a real PAT token).
# It is generated at deploy time by copying from the prt-simulator namespace.
# Kubernetes secrets are namespace-scoped — the prt-simulator one cannot be reused.
GHCR_SECRET_FILE="${SCRIPT_DIR}/ghcr-secret.yaml"

if [[ ! -f "${GHCR_SECRET_FILE}" ]]; then
    echo "[1/3] ghcr-secret.yaml not found — generating from prt-simulator namespace..."

    if ! kubectl get secret ghcr-secret -n prt-simulator &>/dev/null; then
        echo "❌ ghcr-secret not found in prt-simulator namespace."
        echo "   Create it first, then re-run this script:"
        echo "   kubectl create secret docker-registry ghcr-secret \\"
        echo "     --docker-server=ghcr.io \\"
        echo "     --docker-username=<github-username> \\"
        echo "     --docker-password=<CR_PAT> \\"
        echo "     --docker-email=<github-email> \\"
        echo "     -n prt-simulator"
        exit 1
    fi

    # Copy the secret JSON, strip cluster-managed fields, patch namespace + labels,
    # then convert to YAML using python3 (no external plugins needed).
    kubectl get secret ghcr-secret -n prt-simulator -o json \
        | jq 'del(.metadata.resourceVersion, .metadata.uid,
                  .metadata.creationTimestamp, .metadata.annotations,
                  .metadata.managedFields)
               | .metadata.namespace = "cert-parser"
               | .metadata.labels    = {"app": "cert-parser"}' \
        | python3 -c "
import sys, json
s = json.load(sys.stdin)
print('apiVersion:', s['apiVersion'])
print('kind:', s['kind'])
print('metadata:')
print('  name:', s['metadata']['name'])
print('  namespace:', s['metadata']['namespace'])
print('  labels:')
for k, v in s['metadata']['labels'].items():
    print(f'    {k}: {v}')
print('type:', s['type'])
print('data:')
for k, v in s['data'].items():
    print(f'  {k}: {v}')
" > "${GHCR_SECRET_FILE}"

    echo "✓ ghcr-secret.yaml generated"
else
    echo "[1/3] ghcr-secret.yaml already exists — skipping generation"
fi
echo ""

# ── Step 2: apply all manifests ───────────────────────────────────────────────
echo "[2/3] Applying manifests (kubectl apply -k deployment/)..."
kubectl apply -k "${SCRIPT_DIR}" ${DRY_RUN}
echo ""

# ── Step 3: wait for rollout ──────────────────────────────────────────────────
if [[ -z "${DRY_RUN}" ]]; then
    # Force a rollout restart so Kubernetes re-pulls :latest from GHCR.
    # Without this, a running pod that already has :latest cached will NOT
    # be replaced even if the registry image changed (same tag, new digest).
    echo "[3/3] Forcing rollout restart to pull the latest image from GHCR..."
    kubectl rollout restart deployment/cert-parser -n "${NAMESPACE}"
    kubectl rollout status  deployment/cert-parser -n "${NAMESPACE}" --timeout=120s
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✓ Deployment complete!"
    echo ""
    kubectl get deployment,pods,svc -l app=cert-parser -n "${NAMESPACE}"
    echo ""
    echo "Useful commands:"
    echo "  Logs:     kubectl logs -f -l app=cert-parser -n ${NAMESPACE}"
    echo "  Trigger:  kubectl port-forward svc/cert-parser 8000:8000 -n ${NAMESPACE}"
    echo "            curl -X POST http://localhost:8000/trigger"
    echo "  Undeploy: ./deployment/undeploy.sh"
else
    echo "[3/3] Dry-run complete — no changes applied."
fi
