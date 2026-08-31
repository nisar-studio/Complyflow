# ============================================================
# ComplyFlow Backend — Production Dockerfile
# Local-first, self-hosted, zero Google Cloud requirements
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Final Production Image ---
FROM python:3.11-slim

WORKDIR /app

# Create non-root system user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

# Copy installed wheels from builder stage
# useradd -d /app sets home to /app, so Python finds packages in /app/.local
COPY --from=builder /root/.local /app/.local
ENV PATH=/app/.local/bin:$PATH

# Copy application source code
COPY --chown=appuser:appgroup app /app/app

# Create directory for SQLite DB and file uploads with proper ownership
RUN mkdir -p /app/data /app/uploads && chown -R appuser:appgroup /app/data /app/uploads

# Environment settings
ENV APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/app/data/complyflow.db \
    UPLOAD_DIR=/app/uploads \
    PORT=8000

USER appuser

EXPOSE 8000

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start production server
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
