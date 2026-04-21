# ──────────────────────────────────────────────────────────────────────────────
# Builder stage (for hot-reload dev)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libpq-dev \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=development

EXPOSE 8000

CMD ["/app/scripts/start-api.sh"]

# ──────────────────────────────────────────────────────────────────────────────
# Runtime stage (production - minimal, non-root)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

USER appuser

EXPOSE 8000

CMD ["/app/scripts/start-api.sh"]