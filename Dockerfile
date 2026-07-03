# ──────────────────────────────────────────────
# Dockerfile for IVASMS OTP Telegram Bot
# Multi-stage build keeps the final image small.
# ──────────────────────────────────────────────

FROM python:3.11-slim AS builder

# Build deps for lxml / brotli
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libbrotli-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim AS runtime

# Runtime libs for lxml / brotli
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libbrotli1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY . .

# Persistent data dir (mount a Railway volume here)
RUN mkdir -p /data
VOLUME ["/data"]

# Railway injects $PORT — our health server listens on it.
# We also fall back to 8080 for local docker runs.
ENV HEALTH_PORT=${PORT:-8080} \
    DATABASE_PATH=/data/ivasms_bot.db

EXPOSE 8080

# Healthcheck: hit our own /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${HEALTH_PORT}/health || exit 1

CMD ["python", "-m", "bot.main"]
