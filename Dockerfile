# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable


FROM python:3.13-slim AS runtime

ENV ANALYTICS_PROVIDER=mock \
    APP_ENVIRONMENT=development \
    PATH="/app/.venv/bin:$PATH" \
    PREVIEW_ENABLED=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 gateway \
    && useradd --system --uid 10001 --gid gateway \
        --home-dir /nonexistent --no-create-home gateway

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "genai_usage_observability_gateway.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
