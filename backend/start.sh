#!/usr/bin/env sh
set -eu

PORT="${PORT:-8000}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

if [ -n "${DATABASE_URL:-}" ]; then
  # Normalize common Railway/Heroku style scheme.
  DATABASE_URL="$(echo "$DATABASE_URL" | sed 's/^postgres:\/\//postgresql:\/\//')"
  export DATABASE_URL
fi

echo "[start] Running alembic upgrade head..."
alembic upgrade head

echo "[start] Starting uvicorn on 0.0.0.0:${PORT}..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
