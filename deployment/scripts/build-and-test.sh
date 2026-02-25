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

# Start container (no real credentials — only testing that it starts)
CONTAINER_ID=$(docker run -d \
  --health-cmd='curl -f http://localhost:8000/health || exit 1' \
  --health-interval=5s \
  --health-timeout=2s \
  --health-retries=3 \
  "${IMAGE_NAME}")

sleep 3

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
