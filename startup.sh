#!/usr/bin/env bash
set -euo pipefail

echo "Starting Take A Number..."

if [ "${APP_ENV:-}" != "production" ]; then
  echo "ERROR: APP_ENV must be set to production"
  exit 1
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is required"
  exit 1
fi
export FLASK_SKIP_DOTENV=1
python -c 'import pyodbc; import sys; sys.exit(0 if "ODBC Driver 18 for SQL Server" in pyodbc.drivers() else "ERROR: Microsoft ODBC Driver 18 is required")'
# Factory validates production settings; the wrapper owns schema state and locking.
python -m flask --app app:create_app deploy-upgrade

exec gunicorn \
  --bind "0.0.0.0:${PORT:-8000}" \
  --worker-class gthread \
  --workers 1 \
  --threads 100 \
  --timeout 120 \
  --error-logfile - \
  --access-logfile /dev/null \
  --log-level warning \
  'app:create_app()'