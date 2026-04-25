# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Base image shared by stages
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    HF_HOME=/opt/butler/cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/butler/cache/sentence-transformers

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# -----------------------------------------------------------------------------
# Dependency layer
# -----------------------------------------------------------------------------
FROM base AS deps

COPY backend/packages/butler-core/pyproject.toml /tmp/butler-core/pyproject.toml
COPY backend/packages/butler-ml-runtime/pyproject.toml /tmp/butler-ml-runtime/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv --python 3.12 && \
    . /opt/venv/bin/activate && \
    uv pip install --upgrade pip setuptools wheel && \
    uv pip install "sentence-transformers[onnx]>=3.0" "onnxruntime>=1.18" \
                   "numpy>=1.26" "pydantic>=2.7" "structlog>=24.1"

# -----------------------------------------------------------------------------
# Model cache layer
# -----------------------------------------------------------------------------
FROM deps AS model-cache

ENV PATH="/opt/venv/bin:$PATH"

RUN --mount=type=cache,target=/opt/butler/cache/huggingface \
    --mount=type=cache,target=/opt/butler/cache/sentence-transformers \
    python - <<'PY'
from sentence_transformers import SentenceTransformer
model_name = "intfloat/multilingual-e5-small"
model = SentenceTransformer(model_name)
print(f"Downloaded embedding model: {model_name}")
PY

# -----------------------------------------------------------------------------
# Builder stage
# -----------------------------------------------------------------------------
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

COPY backend/requirements.txt /tmp/requirements.txt
COPY backend/pyproject.toml /tmp/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/pip \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r /tmp/requirements.txt

# Copy only what Butler actually needs at runtime/build time
COPY backend /app/backend
COPY scripts /app/scripts
COPY searxng /app/searxng

# -----------------------------------------------------------------------------
# Development stage
# -----------------------------------------------------------------------------
FROM builder AS dev

ENV APP_ENV=development \
    PYTHONPATH=/app:/app/backend/integrations/hermes \
    PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

CMD ["/app/scripts/start-api.sh"]

# -----------------------------------------------------------------------------
# Production runtime stage
# -----------------------------------------------------------------------------
FROM base AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/butler/cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/butler/cache/sentence-transformers

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* && \
    groupadd --system app && \
    useradd --system --gid app --create-home --home-dir /home/app app

COPY --from=deps /opt/venv /opt/venv
COPY --from=model-cache /opt/butler/cache /opt/butler/cache
COPY backend /app/backend
COPY scripts /app/scripts
COPY searxng /app/searxng

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e /app/backend/packages/butler-core && \
    uv pip install --system -e /app/backend/packages/butler-ml-runtime[onnx]

RUN chown -R app:app /app /opt/venv /opt/butler && \
    chmod +x /app/scripts/start-api.sh

ENV APP_ENV=production \
    PYTHONPATH=/app:/app/backend/integrations/hermes

USER app

EXPOSE 8000

CMD ["/app/scripts/start-api.sh"]
