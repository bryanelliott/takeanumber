#!/usr/bin/env bash
set -euo pipefail
test "${APP_ENV:-}" = production

# App Service's Python build supplies the active virtual environment and working directory.
# Never run migrations here: startup/restarts must not change the database schema.
exec gunicorn --bind 0.0.0.0:8000 --worker-class gthread --workers 1 --threads 100 \
  --timeout 120 --error-logfile - --log-level warning 'app:create_app()'
