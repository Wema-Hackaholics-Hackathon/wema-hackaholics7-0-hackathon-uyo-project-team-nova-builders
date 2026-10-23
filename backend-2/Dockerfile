# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first — leverage Docker layer cache
COPY pyproject.toml uv.lock* ./

# Install dependencies into /app/.venv (no system-site, reproducible)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY app/ ./app/

# Install the project itself (registers entry-point scripts)
RUN uv sync --frozen --no-dev


# ── Runtime stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# OpenCV headless needs libGL / libglib — minimal set only
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtualenv and app source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app   /app/app

# Uploads directory (mount a volume here in production for persistence)
RUN mkdir -p uploads/avatars uploads/liveness uploads/proof_of_address uploads

# Make sure the venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user for security
RUN addgroup --system foid && adduser --system --ingroup foid foid
RUN chown -R foid:foid /app
USER foid

EXPOSE 8000

# DATABASE_URL defaults to SQLite inside the container — override with a
# PostgreSQL URL via -e or --env-file for persistent / production use.
ENV DATABASE_URL="sqlite+aiosqlite:///./foid.db"

# Healthcheck — relies on the /health endpoint defined in app/main.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python - <<'EOF'
import urllib.request, sys
try:
    urllib.request.urlopen("http://localhost:8000/health", timeout=8)
    sys.exit(0)
except Exception:
    sys.exit(1)
EOF

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
