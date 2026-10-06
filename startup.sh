#!/usr/bin/env bash
set -euo pipefail

echo "Starting Take A Number..."
echo "APP_ENV=${APP_ENV:-<not set>}"
echo "PORT=${PORT:-8000}"

if [ "${APP_ENV:-}" != "production" ]; then
  echo "ERROR: APP_ENV must be set to production"
  exit 1
fi

exec gunicorn \
  --bind "0.0.0.0:${PORT:-8000}" \
  --worker-class gthread \
  --workers 1 \
  --threads 100 \
  --timeout 120 \
  --error-logfile - \
  --access-logfile - \
  --log-level info \
  'app:create_app()'