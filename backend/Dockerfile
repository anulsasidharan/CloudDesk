# Build with the repository root as context:  docker build -f backend/Dockerfile .
# Pin the base image by digest before production.

# ---- build stage: resolve dependencies into a virtualenv ----
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- runtime stage: no build tools, non-root ----
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /srv
COPY --from=build /srv/.venv /srv/.venv
COPY backend ./backend
COPY agents ./agents
COPY rag ./rag
COPY memory ./memory
COPY integrations ./integrations
COPY sample_data ./sample_data
RUN mkdir -p /srv/data && chown -R app:app /srv/data
ENV PATH="/srv/.venv/bin:$PATH" \
    PYTHONPATH="/srv/backend:/srv" \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL="sqlite+aiosqlite:////srv/data/support.db" \
    CHECKPOINT_DB_PATH="/srv/data/checkpoints.db"
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
