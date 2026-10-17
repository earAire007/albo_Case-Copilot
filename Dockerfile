# Spec 08: one service, the copilot API + worker on :8001, serving the console build.

FROM node:22.11.0-slim AS console
WORKDIR /console
COPY console/package.json console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY console/ ./
RUN npx tsc --noEmit && npx vite build

FROM python:3.12.7-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ backend/
COPY mcp_server/ mcp_server/
COPY data/ data/
COPY --from=console /console/dist console/dist
ENV PYTHONPATH=/app PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 copilot && mkdir -p /app/var && chown copilot /app/var
USER copilot
EXPOSE 8001
CMD ["uvicorn", "backend.app.api:_production_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
