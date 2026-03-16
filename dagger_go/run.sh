#!/bin/bash
# Run the Python CI/CD Dagger pipeline.
# Project name is auto-discovered from pyproject.toml.
#
# Required env vars (loaded from credentials/.env or exported):
#   CR_PAT      - Personal access token for the container registry / git host
#   USERNAME    - Your username on the git host
#
# Repository & registry configuration (optional — sensible defaults):
#   GIT_HOST           - Git server host (default: github.com)
#   REGISTRY           - Container registry (default: ghcr.io)
#   GIT_AUTH_USERNAME  - HTTP auth user for git clone (default: x-access-token)
#   REPO_NAME          - Repository name (auto-detected from parent dir if unset)
#   GIT_BRANCH         - Branch to build (default: main)
#   IMAGE_NAME         - Docker image name (default: Docker-safe project name)
#
# Examples:
#   ./run.sh                                           # GitHub + GHCR (defaults)
#   GIT_HOST=gitlab.com REGISTRY=registry.gitlab.com GIT_AUTH_USERNAME=oauth2 ./run.sh
#   GIT_HOST=gitea.mycompany.com REGISTRY=registry.mycompany.com ./run.sh

set -e

# Load credentials from .env file if present
if [ -f "credentials/.env" ]; then
    set -a
    source credentials/.env
    set +a
fi

# Auto-discover REPO_NAME from parent directory name if not set
if [ -z "$REPO_NAME" ]; then
    REPO_NAME=$(basename "$(cd .. && pwd)")
    export REPO_NAME
fi

# Check required environment variables
if [ -z "$CR_PAT" ]; then
    echo "❌ CR_PAT environment variable is not set"
    echo "   Set it to your Personal Access Token with registry write access"
    exit 1
fi

if [ -z "$USERNAME" ]; then
    echo "❌ USERNAME environment variable is not set"
    echo "   Set it to your username on the git host"
    exit 1
fi

echo "🚀 Running Python CI/CD Pipeline"
echo "   Repository: ${REPO_NAME}"
echo "   Git Host:   ${GIT_HOST:-github.com}"
echo "   Registry:   ${REGISTRY:-ghcr.io}"
echo "   User:       $USERNAME"
echo "   Branch:     ${GIT_BRANCH:-main}"
echo ""

# Always rebuild the binary to ensure it reflects the latest source
echo "📦 Building pipeline binary..."
go build -o cert-parser-dagger-go main.go

# Run the pipeline binary
./cert-parser-dagger-go
