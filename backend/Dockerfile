# Backend: FastAPI + Gemini Live voice agent.
# Built by docker-compose.yml at the repo root; see README "Run with Docker".
FROM python:3.13-slim

RUN pip install --no-cache-dir "uv>=0.8" \
    && useradd --create-home --uid 10001 app

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && chmod +x scripts/docker-entrypoint.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
