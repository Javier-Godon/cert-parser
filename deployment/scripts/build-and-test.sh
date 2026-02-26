#!/bin/bash
# build-and-test.sh — Build Docker image and run local smoke tests (no K8s needed)
# Usage: ./deployment/scripts/build-and-test.sh [version]

set -euo pipefail

VERSION=${1:-"v0.1.0"}
IMAGE_NAME="cert-parser:${VERSION}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Building ${IMAGE_NAME}..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker build \
  --progress=plain \
  -t "${IMAGE_NAME}" \
  -t "cert-parser:latest" \
  .

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Image built successfully: ${IMAGE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker images "${IMAGE_NAME}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing image locally..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Start container with all required env vars (pydantic-settings validates at startup).
# Values are fake — RUN_ON_STARTUP=false prevents any actual pipeline execution.
# Adapters create httpx/psycopg connections lazily, so no real network calls happen.
CONTAINER_ID=$(docker run -d \
  -e AUTH__URL="http://localhost/fake-oidc" \
  -e AUTH__CLIENT_ID="smoke-test-client" \
  -e AUTH__CLIENT_SECRET="smoke-test-secret" \
  -e AUTH__USERNAME="smoke-test-user" \
  -e AUTH__PASSWORD="smoke-test-password" \
  -e LOGIN__URL="http://localhost/fake-login" \
  -e LOGIN__BORDER_POST_ID="1" \
  -e LOGIN__BOX_ID="1" \
  -e LOGIN__PASSENGER_CONTROL_TYPE="1" \
  -e DOWNLOAD__URL="http://localhost/fake-download" \
  -e DATABASE__HOST="localhost" \
  -e DATABASE__NAME="cert_parser_db" \
  -e DATABASE__USERNAME="cert_parser" \
  -e DATABASE__PASSWORD="smoke-test-db-password" \
  -e RUN_ON_STARTUP="false" \
  -e LOG_LEVEL="WARNING" \
  --health-cmd='curl -f http://localhost:8000/health || exit 1' \
  --health-interval=5s \
  --health-timeout=2s \
  --health-retries=3 \
  "${IMAGE_NAME}")

sleep 5

echo "[Test 1] Checking /health endpoint..."
docker exec "${CONTAINER_ID}" curl -sf http://localhost:8000/health || {
  echo "❌ Health check failed"
  docker logs "${CONTAINER_ID}"
  docker rm -f "${CONTAINER_ID}"
  exit 1
}
echo "✓ /health OK"

echo "[Test 2] Checking /info endpoint..."
docker exec "${CONTAINER_ID}" curl -sf http://localhost:8000/info || {
  echo "❌ /info endpoint failed"
  docker logs "${CONTAINER_ID}"
  docker rm -f "${CONTAINER_ID}"
  exit 1
}
echo "✓ /info OK"

echo "[Test 3] Checking container health status..."
docker inspect --format='Health status: {{json .State.Health.Status}}' "${CONTAINER_ID}"

echo ""
echo "Cleaning up container..."
docker rm -f "${CONTAINER_ID}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ All tests passed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
