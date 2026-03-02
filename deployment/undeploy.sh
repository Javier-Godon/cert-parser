#!/bin/bash
# undeploy.sh — Remove cert-parser from Kubernetes.
#
# Deletes the cert-parser namespace and all resources inside it
# (Deployment, Service, ConfigMap, Secrets, NetworkPolicy, PDB).
# Deleting the namespace is the cleanest approach — it cascades to all resources.
#
# The ghcr-secret.yaml file on disk is also removed so that the next
# deploy.sh run re-generates it fresh from the cluster.
#
# Usage:
#   ./deployment/undeploy.sh           # remove everything (prompts for confirmation)
#   ./deployment/undeploy.sh --force   # skip confirmation prompt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="cert-parser"
FORCE=""

if [[ "${1:-}" == "--force" ]]; then
    FORCE="yes"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "cert-parser — Kubernetes undeploy"
echo "  Namespace: ${NAMESPACE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Confirm ───────────────────────────────────────────────────────────────────
if [[ -z "${FORCE}" ]]; then
    read -r -p "This will delete the '${NAMESPACE}' namespace and ALL its resources. Continue? [y/N] " confirm
    if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# ── Delete namespace (cascades to all resources inside it) ────────────────────
echo "[1/2] Deleting namespace '${NAMESPACE}'..."
if kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    kubectl delete namespace "${NAMESPACE}"
    echo "✓ Namespace '${NAMESPACE}' deleted (all resources removed)"
else
    echo "⚠  Namespace '${NAMESPACE}' not found — nothing to delete"
fi
echo ""

# ── Clean up the local gitignored ghcr-secret.yaml ────────────────────────────
# Remove it so the next deploy.sh run re-generates it from the cluster.
GHCR_SECRET_FILE="${SCRIPT_DIR}/ghcr-secret.yaml"
echo "[2/2] Cleaning up local ghcr-secret.yaml..."
if [[ -f "${GHCR_SECRET_FILE}" ]]; then
    rm -f "${GHCR_SECRET_FILE}"
    echo "✓ ghcr-secret.yaml removed (will be regenerated on next deploy)"
else
    echo "⚠  ghcr-secret.yaml not found — skipping"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Undeploy complete."
echo ""
echo "To redeploy:  ./deployment/deploy.sh"

