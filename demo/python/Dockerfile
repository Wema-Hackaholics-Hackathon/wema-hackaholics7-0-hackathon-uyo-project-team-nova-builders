# Harbor demo — React app + Python backend (foid SDK) in one image.
# Build context is demo/:  docker compose up python --build
FROM node:22-alpine AS web
WORKDIR /web
COPY package.json package-lock.json ./
COPY vendor ./vendor
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 \
    DEMO_DIST_DIR=/app/dist DEMO_KEYS_DIR=/app/keys HOST=127.0.0.1 PORT=3100
WORKDIR /app/python
# The SDK comes in as a packaged wheel (vendor/), the way it would from PyPI.
COPY python/pyproject.toml python/uv.lock ./
COPY python/vendor ./vendor
RUN uv sync --frozen --no-install-project
COPY python/app.py ./
COPY --from=web /web/dist /app/dist
EXPOSE 3100
CMD ["sh", "-c", "exec uvicorn app:app --host \"$HOST\" --port \"$PORT\""]
