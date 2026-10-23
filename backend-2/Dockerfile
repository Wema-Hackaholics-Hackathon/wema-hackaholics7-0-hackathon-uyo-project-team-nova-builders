# ── Build stage ────────────────────────────────────────────────────────────────
#
# Build from the REPO ROOT so both backend-2/ and frontend/ are in context:
#
#   docker build -f backend-2/Dockerfile -t foid-backend .
#
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first — leverage Docker layer cache
COPY backend-2/pyproject.toml backend-2/uv.lock* ./

# Install dependencies into /app/.venv (no system-site, reproducible)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source + logo (email templates load it at runtime via
# the second candidate path: app/services/logo-white.png)
COPY backend-2/app/ ./app/
COPY frontend/public/logo-white.png ./app/services/logo-white.png

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

# Copy the virtualenv and app source from builder (logo bundled inside app/)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app   /app/app

# Uploads directory — mount a named volume here in production for persistence:
#   docker run -v foid_uploads:/app/uploads ...
RUN mkdir -p uploads/avatars uploads/liveness uploads/proof_of_address

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
# NOTE: heredoc syntax is not valid in HEALTHCHECK CMD; use -c instead.
#       127.0.0.1 is used because the app binds on 0.0.0.0 inside the container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "\
import urllib.request, sys; \
r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=8); \
sys.exit(0 if r.status == 200 else 1)"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
