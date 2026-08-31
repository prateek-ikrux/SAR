# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies resolve from the lockfile in their own layer, so editing app code
# does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

# curl is only here for the healthcheck; it is a few hundred KB and saves
# hand-rolling a Python probe.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

USER app
EXPOSE 8000

# No .env is baked in - configuration arrives through the environment at run
# time, so the same image is safe to promote between environments.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# --no-proxy-headers is not optional here. Uvicorn trusts X-Forwarded-For by
# default and rewrites the client address from it, which would hand the app a
# value any caller can forge - and per-IP rate limiting keyed on a forgeable
# address is no rate limiting at all. The app decides for itself whether to
# believe that header, via TRUST_PROXY_HEADERS.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
