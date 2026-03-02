# Multi-stage production Dockerfile for cert-parser
# Build stage optimizes for layer caching and image size
# Runtime stage uses slim Python image with non-root user

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ STAGE 1: Builder ━━━━━━━━━━━━━━━━━━
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build dependencies (git, build-essential for binary packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files (README.md required by hatchling metadata validation)
COPY pyproject.toml pyproject.toml
COPY README.md README.md
COPY python_framework/ python_framework/
COPY src/ src/

# Create the venv at /app/venv — the SAME path used in the runtime stage.
# This ensures all pip-generated entry-point scripts have the correct shebang
# (#!/app/venv/bin/python) and are executable in the runtime container.
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel && \
    pip install "./python_framework" && \
    pip install ".[server]"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ STAGE 2: Runtime ━━━━━━━━━━━━━━━━━
FROM python:3.14-slim

LABEL maintainer="BlueSolution"
LABEL description="cert-parser: ICAO Master List certificate parser for Kubernetes"

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash certparser

# Copy Python virtual environment from builder (shebangs point to /app/venv/bin/python ✓)
COPY --from=builder --chown=certparser:certparser /app/venv /app/venv

# Copy application source
COPY --chown=certparser:certparser src/ /app/src/

# Set Python environment variables
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Switch to non-root user
USER certparser

# Health check: curl /health endpoint (requires curl to be installed above)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Use python -m uvicorn instead of the entry-point script to avoid any
# shebang resolution issues across platforms and base image variants.
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["cert_parser.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
