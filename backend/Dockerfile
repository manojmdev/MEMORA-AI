# ==============================================================================
# MEMORA AI — Production Backend Dockerfile
# Optimized for Python 3.12, FastAPI, asyncpg & SSL connection to Neon Postgres
# ==============================================================================

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install system certificates for SSL database connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source
COPY backend/app /app/app

# Create non-root runtime user for container security
RUN adduser --disabled-password --gecos "" memora && \
    chown -R memora:memora /app
USER memora

EXPOSE 8000

# Healthcheck targeting FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Production server entrypoint
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
