# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Runtime image ----
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY . .

# Copy and set entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Default environment
ENV SERVICE_TYPE=api
ENV PYTHONUNBUFFERED=1

# Health check for API service (ignored by worker/beat)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD if [ "$SERVICE_TYPE" = "api" ]; then curl -f http://localhost:8000/health || exit 1; else exit 0; fi

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
