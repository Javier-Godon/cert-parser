#!/bin/bash
# build-and-test.sh — Build Docker image and run local tests
# Usage: ./k8s/scripts/build-and-test.sh [version]

set -euo pipefail

VERSION=${1:-"v0.1.0"}
IMAGE_NAME="cert-parser:${VERSION}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Building ${IMAGE_NAME}..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Build image
docker build \
  --progress=plain \
  -t "${IMAGE_NAME}" \
  -t "cert-parser:latest" \
  .

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Image built successfully: ${IMAGE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show image info
docker images "${IMAGE_NAME}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing image locally..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: Check if image runs without error
echo "[Test 1] Starting container..."
CONTAINER_ID=$(docker run -d \
  --health-cmd='curl -f http://localhost:8000/health || exit 1' \
  --health-interval=5s \
  --health-timeout=2s \
  --health-retries=3 \
  "${IMAGE_NAME}")

sleep 2

echo "[Test 2] Checking health endpoint..."
docker exec "${CONTAINER_ID}" curl -s http://localhost:8000/health || {
  echo "❌ Health check failed"
  docker logs "${CONTAINER_ID}"
  docker rm -f "${CONTAINER_ID}"
  exit 1
}

echo "✓ Health check passed"

echo "[Test 3] Checking info endpoint..."
docker exec "${CONTAINER_ID}" curl -s http://localhost:8000/info || {
  echo "❌ Info endpoint failed"
  docker logs "${CONTAINER_ID}"
  docker rm -f "${CONTAINER_ID}"
  exit 1
}

echo "✓ Info endpoint passed"

# Check health status
echo ""
echo "[Test 4] Checking container health status..."
docker inspect --format='{{json .State.Health.Status}}' "${CONTAINER_ID}"

# Clean up
echo ""
echo "Cleaning up..."
docker rm -f "${CONTAINER_ID}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ All tests passed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Push to registry: docker push ${IMAGE_NAME}"
echo "  2. Deploy to K8s: kubectl apply -f k8s/"
echo "  3. Check deployment: kubectl get deployment,pods,svc"
echo ""
