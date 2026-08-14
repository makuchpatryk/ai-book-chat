# Dev image — used by both the `api` and `worker` compose services.
# Source is bind-mounted at runtime, so the copy below only seeds the image.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

WORKDIR /app

# Dependency layer — cached until pyproject/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the cl100k_base BPE file into the image so the worker never downloads it
# mid-task (TIKTOKEN_CACHE_DIR above is where tiktoken looks at runtime).
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev

# uid 1000 matches the typical host user, so bind-mounted sources stay writable.
RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /app /data/uploads /opt/venv
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
