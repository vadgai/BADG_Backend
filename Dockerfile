# ============================================
# VADG Backend - Production Dockerfile
# Optimized for Google Cloud Run
# ============================================

FROM python:3.11-slim as builder

# Build arguments
ARG PYTHON_VERSION=3.11
ARG WORKDIR=/app

# Noninteractive APT
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR ${WORKDIR}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libcairo2-dev \
    libgirepository1.0-dev \
    python3-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Pin spaCy model (spacy download can 404 with missing version in Docker)
RUN pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# ============================================
# Final production image
# ============================================
FROM python:3.11-slim

# Security: Create non-root user
RUN useradd -m -u 1000 vadg && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=vadg:vadg . .

# Set environment variables
ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Switch to non-root user for security
USER vadg

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the application
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info

# ============================================
# Build & Run Instructions:
# 
# Build:
#   docker build -t vadg-backend .
# 
# Run locally:
#   docker run -p 8080:8080 \
#     -e GOOGLE_API_KEY=your_key \
#     -e ALLOWED_ORIGINS=http://localhost:5173 \
#     vadg-backend
#
# Deploy to Google Cloud Run:
#   gcloud run deploy vadg-backend \
#     --region=asia-south1 \
#     --source . \
#     --allow-unauthenticated
# ============================================
