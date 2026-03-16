#!/bin/bash
# Corporate pipeline runner with MITM proxy and custom CA support.
# Compiles and runs the corporate_main.go variant.
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
# Corporate-specific:
#   HTTP_PROXY / HTTPS_PROXY  - Corporate MITM proxy URL
#   DEBUG_CERTS=true          - Enable certificate discovery diagnostics
#   CA_CERTIFICATES_PATH=...  - Colon-separated paths to CA certs
#
# Examples:
#   ./run-corporate.sh                                             # GitHub + GHCR
#   GIT_HOST=gitlab.com REGISTRY=registry.gitlab.com GIT_AUTH_USERNAME=oauth2 ./run-corporate.sh

set -e

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check prerequisites
PROJECT_NAME=$(basename "$(cd .. && pwd)")
echo -e "${BLUE}🏢 ${PROJECT_NAME} — Corporate CI/CD Pipeline Runner${NC}"
echo ""

# Auto-discover REPO_NAME from parent directory name if not already set
if [ -z "$REPO_NAME" ]; then
    REPO_NAME=$(basename "$(cd .. && pwd)")
    export REPO_NAME
fi
echo "   Repository: ${REPO_NAME}"
echo ""

# Verify credentials
if [ ! -f "credentials/.env" ]; then
    echo -e "${YELLOW}⚠️  credentials/.env not found${NC}"
    echo "   Create it with:"
    echo "   cat > credentials/.env << EOF"
    echo "   CR_PAT=your_registry_token"
    echo "   USERNAME=your_username"
    echo "   # Optional: corporate settings"
    echo "   GIT_HOST=github.com"
    echo "   REGISTRY=ghcr.io"
    echo "   GIT_AUTH_USERNAME=x-access-token"
    echo "   HTTP_PROXY=http://proxy.company.com:8080"
    echo "   HTTPS_PROXY=https://proxy.company.com:8080"
    echo "   EOF"
    exit 1
fi

# Load environment
set -a
source credentials/.env
set +a

# Check for CA certificates
if [ -d "credentials/certs" ]; then
    cert_count=$(find credentials/certs -name "*.pem" 2>/dev/null | wc -l)
    if [ "$cert_count" -gt 0 ]; then
        echo -e "${GREEN}✓ Found $cert_count CA certificate(s)${NC}"
    else
        echo -e "${YELLOW}⚠️  credentials/certs/ exists but no .pem files found${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No credentials/certs/ directory - corporate CA support disabled${NC}"
    echo "   Create with: mkdir -p credentials/certs"
    echo "   Then copy .pem files into it"
fi

# Check proxy configuration
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo -e "${GREEN}✓ Proxy configured${NC}"
    [ -n "$HTTP_PROXY" ] && echo "   HTTP_PROXY=$HTTP_PROXY"
    [ -n "$HTTPS_PROXY" ] && echo "   HTTPS_PROXY=$HTTPS_PROXY"
else
    echo -e "${YELLOW}⚠️  No proxy configured (OK if not needed)${NC}"
fi

echo ""

# Compile corporate version
echo -e "${BLUE}Compiling corporate pipeline...${NC}"

# Build with corporate build tag
if go build -tags corporate -o cert-parser-corporate-dagger-go corporate_main.go 2>&1; then
    echo -e "${GREEN}✓ Build successful${NC}"
else
    echo -e "${YELLOW}❌ Build failed${NC}"
    exit 1
fi

echo ""

# Run pipeline
echo -e "${BLUE}🚀 Executing corporate pipeline...${NC}"
echo ""

if [ "$DEBUG_CERTS" = "true" ]; then
    echo -e "${YELLOW}Debug mode enabled - will show certificate diagnostics${NC}"
    echo ""
fi

./cert-parser-corporate-dagger-go

echo ""
echo -e "${GREEN}✅ Pipeline completed${NC}"
