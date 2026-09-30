# Take A Number

A Flask/PostgreSQL application for student help queues in college labs.
Milestones 0–1 provide the Flask/PostgreSQL foundation and instructor sign-up,
login, logout, and a protected dashboard placeholder. Help sessions and queues
follow in later milestones; see `docs/implementation-plan.md`.

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
flask --app app:create_app db upgrade
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

Open http://127.0.0.1:5000/auth/signup to create an instructor account, then log in
at `/auth/login`. `/instructor/dashboard` requires login; logout uses a CSRF-protected
POST form. Students do not sign up. Sign-up is self-service; email ownership and
institutional affiliation are not verified in this milestone. Password recovery,
SSO, administrator roles, and student authentication are not implemented.

## Instructor authentication policy

- Email whitespace is trimmed and the entire address is lowercased, including the
  local part. Internationalized domains are converted to ASCII IDNA form. Unicode
  local parts are rejected. Dots and `+tags` are preserved; they are not aliases.
  Email syntax is checked without DNS/deliverability requests. PostgreSQL enforces
  unique normalized emails, including simultaneous sign-ups.
- Display names are required, trimmed, and limited to 100 characters.
- Passwords are 15–128 characters, are not trimmed or silently truncated, and can
  contain spaces. Only salted Werkzeug `scrypt:32768:8:3` hashes are stored. This
  work factor follows an [OWASP scrypt configuration](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt).
- Sign-up returns to login. Login clears the previous session before signing in;
  no remember-me cookie is requested. Login always returns to the dashboard and
  ignores `next` values. Unknown emails, wrong passwords, and inactive accounts
  receive the same login error. Inactive accounts also lose existing access.
- All POST forms require CSRF tokens. Auth requests are limited to 64 KiB by the
  application request-size limit.
- Sign-up/login POSTs share a per-client-address limit of 20 attempts per fixed
  15-minute window, including invalid-CSRF attempts. Rejection returns HTTP 429
  and `Retry-After`. The thread-safe limiter stores addresses only in bounded
  process memory; it resets on restart and assumes the documented single worker.
  Forwarding headers are not trusted. A future proxy deployment must explicitly
  configure trustworthy client addresses; otherwise clients behind that proxy
  share its limit. Clients behind the same NAT also share a limit.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required secret for Flask/CSRF. |
| `DATABASE_URL` | Required for ordinary app instances; PostgreSQL URL using psycopg. |
| `TEST_DATABASE_URL` | Required for test instances; never falls back to `DATABASE_URL`. |
| `SESSION_COOKIE_SECURE` | `true` for HTTPS cookies; `false` for local HTTP (default). |
| `AUTH_RATE_LIMIT` | Positive integer; shared sign-up/login POST limit per address (default 20). |
| `AUTH_RATE_WINDOW_SECONDS` | Positive integer; fixed rate-limit window (default 900). |

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

Authentication tests verify the actual database and role, apply Alembic migrations
only to the dedicated test database, and clean instructor rows between tests. A
migration test downgrades to base and upgrades again on that disposable database.
Tests do not call `create_all` or `drop_all`. Do not run parallel test processes
against this single test database.

## Migrations

`migrations/versions/0001_instructor_create_instructor.py` creates only `instructor`:
UUID primary key, normalized unique email, required display name/hash, active flag,
and UTC-aware creation/update timestamps. ORM updates refresh `updated_at`.

```powershell
flask --app app:create_app db upgrade
flask --app app:create_app db current
# After a future model change, generate and review the migration before upgrading:
flask --app app:create_app db migrate -m "describe the schema change"
```

The initial migration's downgrade removes the instructor table and its account
data. The automated downgrade test runs only on the dedicated test database.

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
  extensions.py    SQLAlchemy, Flask-Migrate, CSRF, Flask-Login
  cli.py           read-only database check
  health/          health blueprint
  models/          Instructor model
  auth/            forms, credential services, routes, authentication throttling
  instructor/      protected dashboard blueprint
  templates/       server-rendered instructor forms and dashboard
migrations/        Alembic configuration and versioned schema
tests/             foundation, authentication, database, and migration tests
compose.yaml       local development and test PostgreSQL servers
pyproject.toml     pytest and Ruff settings
```
