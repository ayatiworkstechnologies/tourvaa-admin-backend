#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  attempts=0
  until python -m alembic upgrade head; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "${MIGRATION_MAX_ATTEMPTS:-30}" ]; then
      echo "Database migration failed after ${attempts} attempts." >&2
      exit 1
    fi
    echo "Database is not ready; retrying migration in 2 seconds (${attempts}/${MIGRATION_MAX_ATTEMPTS:-30})..." >&2
    sleep 2
  done
fi

# Default stays one worker for a zero-config deployment. Scheduled sweep
# locking and WebSocket pub/sub (app/utils/distributed_lock.py,
# app/services/messaging_ws.py) now use Redis when REDIS_URL is set, so
# WEB_CONCURRENCY may be raised above 1 once REDIS_URL points at a real
# shared Redis instance - app.main.validate_worker_concurrency() enforces
# this at startup.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"

