#!/bin/bash
set -e
cd /app/backend

APP_MODULE="${APP_MODULE:-main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
APP_ENV="${APP_ENV:-development}"
LOG_LEVEL="${LOG_LEVEL:-info}"
WORKERS="${WEB_CONCURRENCY:-1}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
PROXY_HEADERS="${PROXY_HEADERS:-true}"
LIMIT_CONCURRENCY="${LIMIT_CONCURRENCY:-1000}"
LIMIT_MAX_REQUESTS="${LIMIT_MAX_REQUESTS:-10000}"
LIMIT_MAX_REQUESTS_JITTER="${LIMIT_MAX_REQUESTS_JITTER:-1000}"
TIMEOUT_WORKER_HEALTHCHECK="${TIMEOUT_WORKER_HEALTHCHECK:-10}"

COMMON_ARGS=(
  "$APP_MODULE"
  --host "$HOST"
  --port "$PORT"
  --log-level "$LOG_LEVEL"
  --loop auto
  --http auto
  --ws auto
  --lifespan auto
  --limit-concurrency "$LIMIT_CONCURRENCY"
  --limit-max-requests "$LIMIT_MAX_REQUESTS"
  --limit-max-requests-jitter "$LIMIT_MAX_REQUESTS_JITTER"
)

if [[ "$PROXY_HEADERS" == "true" ]]; then
  COMMON_ARGS+=(--proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS")
fi

if [[ "$APP_ENV" == "development" ]]; then
  exec python -m uvicorn "${COMMON_ARGS[@]}" --reload
fi

exec python -m uvicorn "${COMMON_ARGS[@]}" \
  --workers "$WORKERS" \
  --timeout-worker-healthcheck "$TIMEOUT_WORKER_HEALTHCHECK"
