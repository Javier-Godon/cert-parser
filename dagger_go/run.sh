#!/bin/bash
# Run the Python CI/CD Dagger pipeline with GitHub registry authentication
# Usage: ./run.sh
# Project name is auto-discovered from pyproject.toml

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
    echo "   Set it to your GitHub Personal Access Token with 'write:packages' scope"
    exit 1
fi

if [ -z "$USERNAME" ]; then
    echo "❌ USERNAME environment variable is not set"
    echo "   Set it to your GitHub username"
    exit 1
fi

echo "🚀 Running Python CI/CD Pipeline"
echo "   Repository: ${REPO_NAME}"
echo "   GitHub User: $USERNAME"
echo "   Branch: ${GIT_BRANCH:-main}"
echo ""

# Check if binary exists, build if not
if [ ! -f ./cert-parser-dagger-go ]; then
    echo "📦 Building pipeline binary..."
    go mod download dagger.io/dagger
    go mod tidy
    go build -o cert-parser-dagger-go main.go
fi

# Run the pipeline binary
./cert-parser-dagger-go
