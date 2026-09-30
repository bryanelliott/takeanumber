# Take A Number

A Flask/PostgreSQL application for student help queues in college labs.
Milestone 0 provides an application factory, environment configuration, health
endpoint, database connectivity command, and tests. Product features follow in
later milestones; see `README-CODEX-START-HERE.md` and `docs/implementation-plan.md`.

## Local setup (Windows PowerShell)

Use Python 3.13 and Docker Desktop with its Linux engine running. Flask runs in
the local virtual environment; PostgreSQL runs in Docker. From the repository root:

```powershell
# Only create the virtual environment if it does not already exist.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check

# Only copy if .env does not already exist; preserve any existing local settings.
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `.env` as `SECRET_KEY`. The factory loads this file
without overriding existing process environment variables. `.env` is ignored by
Git. The database passwords in the example and Compose file are deliberately
local development credentials, not deployment secrets.

```powershell
docker compose config --quiet
docker compose up -d --wait db test-db
flask --app app:create_app check-db
flask --app app:create_app run --debug
```

In a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

`/health` returns HTTP 200 and `{"status":"ok"}` as a process liveness check.
It does not query PostgreSQL. `check-db` executes `SELECT 1` and exits nonzero
if the database connection fails, without printing connection credentials.
The root URL has no page yet.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required secret for Flask/CSRF. |
| `DATABASE_URL` | Required for ordinary app instances; PostgreSQL URL using psycopg. |
| `TEST_DATABASE_URL` | Required for test instances; never falls back to `DATABASE_URL`. |
| `SESSION_COOKIE_SECURE` | `true` for HTTPS cookies; `false` for local HTTP (default). |

Both `postgresql://` and `postgresql+psycopg://` select psycopg 3. SQLite and
other database backends are rejected. `psycopg-binary` is pinned alongside
`psycopg` because the original environment lacked the libpq library needed by
the plain psycopg package. Existing dependency pins are otherwise unchanged.

## Tests and database isolation

In an activated virtual environment, after copying/configuring `.env`:

```powershell
docker compose up -d --wait test-db
ruff check .
pytest
# Optional coverage report:
pytest --cov=app --cov-report=term-missing
```

Tests explicitly create the app with `TESTING=True`. Before any database engine
is initialized, the factory requires a `TEST_DATABASE_URL` with a loopback host,
database and username ending in `_test`, and no URL query parameters. Test and
development database names must differ. Additional SQLAlchemy binds are rejected,
and `SQLALCHEMY_DATABASE_URI` cannot override the selected URL.

Compose provides two separate PostgreSQL servers, each bound only to loopback:

| Service | Host port | Database / user | Storage |
| --- | --- | --- | --- |
| `db` | 55432 | `takeanumber_dev` | Persistent named volume |
| `test-db` | 55433 | `takeanumber_test` | Disposable memory filesystem |

The servers have distinct credentials and do not share database storage. Use
these dedicated local instances; never point tests at a development or production
database. Guards catch configuration mistakes, but names alone cannot prove a
database is disposable. The integration tests verify the actual connected database
and role. Missing configuration or unavailable PostgreSQL fails tests rather than
silently skipping them. Non-loopback CI database support is deferred.

No application schema exists yet, so tests run read-only queries and do not call
`create_all` or `drop_all`. Flask-Migrate is initialized; introduce the migration
repository and first schema migration with the first model in Milestone 1.

## Stop and reset local databases

```powershell
# Stop containers; preserve development data. Test data is disposable.
docker compose down
# Recreate only the disposable test database:
docker compose up -d --wait --force-recreate test-db
# Destructive: remove the local development database volume as well.
docker compose down --volumes
```

If a host port is already in use, change its mapping in `compose.yaml` and the
corresponding URL in `.env` together. If Docker reports a missing engine pipe,
start Docker Desktop and wait for the Linux engine to become ready.

## Foundation layout

```text
app/
  __init__.py       application factory
  config.py        environment settings and database guards
  extensions.py    SQLAlchemy, Flask-Migrate, CSRF
  cli.py           read-only database check
  health/          health blueprint
tests/             smoke, configuration safety, PostgreSQL integration tests
compose.yaml       local development and test PostgreSQL servers
pyproject.toml     pytest and Ruff settings
```
