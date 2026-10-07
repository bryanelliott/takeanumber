# Take A Number

A Flask/SQL Server application for student help queues in college labs.
Milestones 0–6, Phase 7A, and Milestone 8 provide the Flask/SQL Server foundation, instructor authentication,
help sessions, public student queue joining/leaving, Master View advancement, and
live queue updates, wait-time estimates, in-browser student alerts, and instructor settings.
See `docs/implementation-plan.md` for later milestones.
Milestone 10 adds CI and Azure deployment preparation. Milestone 9 metrics remain
unimplemented pending the peak queue history decision.

## Local setup (Windows PowerShell)

Use Python 3.13 and Docker Desktop with its Linux engine running. Flask runs in
the local virtual environment with Microsoft ODBC Driver 18 installed; SQL Server
2022 runs in Docker. Use x86-64 Linux containers and allow at least 2 GB RAM per SQL
Server container. For tests, the supplied Linux runner includes Python and Driver 18.
From the repository root:

```powershell
# Only create the virtual environment if it does not already exist.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check

# Only copy if .env does not already exist; preserve any existing local settings.
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `.env` as `SECRET_KEY`. The factory loads this file
without overriding existing process environment variables. `.env` is ignored by
Git. The database passwords in the example and Compose file are deliberately
local development credentials, not deployment secrets. If upgrading an existing
checkout, replace its old database URLs with the SQL Server examples; do not reuse
the previous engine's data volume or migration history.

Start the development server, then create its dedicated database/login once:

```powershell
docker compose up -d db
# Wait for SQL Server to report ready, then provision local database/user only:
@"
CREATE DATABASE [takeanumber_dev];
GO
ALTER DATABASE [takeanumber_dev] SET READ_COMMITTED_SNAPSHOT ON;
CREATE LOGIN [takeanumber_dev] WITH PASSWORD='Local_Dev_Only_42!', CHECK_POLICY=OFF;
GO
USE [takeanumber_dev];
CREATE USER [takeanumber_dev] FOR LOGIN [takeanumber_dev] WITH DEFAULT_SCHEMA=dbo;
GRANT CONNECT, CREATE TABLE TO [takeanumber_dev];
GRANT CONTROL ON SCHEMA::dbo TO [takeanumber_dev];
GO
"@ | docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Local_Dev_Only_42!' -C -b

flask --app app:create_app check-db
flask --app app:create_app db upgrade
python run.py --debug
```

These local SQL setup commands are for a new development volume only, not repeated
at every launch. Alembic creates application tables. Local containers use self-signed
certificates; `.env.example` permits them only outside production. See Microsoft's
[ODBC installation instructions](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
if the host Python process cannot locate Driver 18.

In a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
```

`/health` returns HTTP 200 and `{"status":"ok"}` as a process liveness check.
It does not query SQL Server. `check-db` executes `SELECT 1` and exits nonzero
if the database connection fails, without printing connection credentials.
The root URL has no page yet.

Open http://127.0.0.1:5000/auth/signup to create an instructor account, then log in
at `/auth/login`. `/instructor/dashboard` requires login; logout uses a CSRF-protected
POST form. Students do not sign up. Sign-up is self-service; email ownership and
institutional affiliation are not verified in this milestone. Password recovery,
SSO, administrator roles, and student authentication are not implemented.

## Instructor help sessions

From the dashboard, select **Start help session** to open its Master View. An
active session replaces the start control with **Open Master View**. Use **End
session** in the Master View to close it; the ended view remains accessible to
its owner and shows the end timestamp. Return to the dashboard to start another.

- `POST /instructor/sessions` starts a session or opens the existing active one.
- `GET /instructor/sessions/<public_code>/master` displays the owner-only Master View.
- `POST /instructor/sessions/<public_code>/end` ends that session once.
- `POST /instructor/sessions/<public_code>/serve-next` starts the displayed Next Up.
- `POST /instructor/sessions/<public_code>/done` completes the displayed serving request
  and starts the next waiting request.
- `GET /instructor/sessions/<public_code>/qr.svg` generates its public Client View QR.

All mutations require login and CSRF. The authenticated instructor determines
ownership; submitted instructor IDs are ignored. Missing sessions and another
instructor's sessions both return 404. Public codes are opaque 128-bit random
values, separate from internal UUIDs, and do not grant management access.

A SQL Server filtered unique index permits only one active session per instructor.
The service locks the instructor row during Start, so simultaneous requests return
the same active session. End locks its session row; repeated or concurrent calls
preserve the first `ended_at` and retain the historical record. An old End request
cannot affect a newly started session. Database constraints also enforce valid
statuses and consistent timestamps. Session deletion is not offered.

`app/services/sessions.py` exposes `session_for_join(public_code)` for queue mutations.
It rejects missing or ended sessions and retains a row lock until the caller's
transaction ends. The queue service checks and inserts in that same
transaction to avoid racing End. The `accepts_joins` model property alone is only
a state snapshot, not permission to insert later.

## Master View (Milestone 4)

The Master View shows Currently Serving, Next Up, the first five waiting requests
(including Next Up), and the full waiting count, excluding the serving request.
Queue numbers and optional names appear on this instructor-controlled display.
Names are HTML-escaped; browser identifiers and hashes are never displayed.

All requests initially wait. If nobody is serving, **Serve next** begins the first
waiting request. **Done** completes the displayed request and starts the next in
one transaction, or leaves nobody serving if the queue is empty. Done without a
current request changes nothing. A serving request that leaves is not completed;
the instructor uses Serve next to resume. Stale/repeated controls target their
original request and cannot accidentally complete its successor.

Join, Leave, Serve next, Done, and End share a session row lock. SQL Server also
enforces at most one serving request per session. Completion and the next service
start share a UTC database timestamp obtained after locking. Multiple Master View
browsers read consistent database snapshots and update automatically after queue
changes. **Refresh queue** remains available. Students can enable in-browser alerts.

The QR encodes the same absolute public URL as **Open student Client View**. It is
generated locally as SVG using the existing `qrcode` dependency. Open the Master
View using an address students can reach: a QR containing `127.0.0.1` or `localhost`
will not reach the instructor's computer from their phones. For local phone testing
on a trusted network, run `python run.py --host=0.0.0.0` without
debug mode and open the Master View using that computer's reachable hostname/IP
and port. Production proxy/HTTPS handling is documented in [deployment.md](docs/deployment.md).

## Student queue (Milestone 3)

Open **Open student Client View** in an active Master View and share that link.
`GET /session/<public_code>` is public and does not require student login.
Students can optionally enter a name and select **Take A Number**, refresh their
number and people-ahead count, **Leave Queue**, or **Exit** to a passive page.
Exit leaves requests unchanged; Return to session restores the current state.

All new requests wait, including the first, until instructor advancement.
Names are optional and not used to identify or merge people.
Each browser sees only its own request. No location, seat/workstation information,
geolocation APIs, or browser fingerprinting is used by the student feature.

The signed, HttpOnly `tan_browser` cookie contains a random 256-bit token. Its
SHA-256 hash is stored only when joining; the raw token is never stored in the
database or placed in URLs. Cookie scope is `/session`, SameSite is Lax, and Secure
follows `SESSION_COOKIE_SECURE`. The default lifetime is 180 days, renewed when
opening the Client View. This is a fallible browser profile, not a verified person:
shared browsers share requests, and clearing cookies or changing browsers can
lose access and permit a separate request. Names do not recover lost identities.

Join and leave are CSRF-protected POSTs. Forms are also bound to the cookie that
rendered them; missing/changed/expired cookies require reopening the view. A POST
never invents a fresh identity when cookies are blocked. Successful POSTs redirect
to GET. Student identity persists independently of instructor login/logout.

The session row lock serializes Join, Leave, and End. Number allocation and entry
creation commit together. SQL Server independently enforces unique session numbers
and one waiting/serving entry per browser identity per session using an explicit
filtered unique index. Duplicate joins return the existing request unchanged.
Leave records a timestamp and retains history. It targets a specific entry, so
replaying an old Leave after rejoining cannot remove the new request.

Ending a session blocks joins/leaves and hides participation controls. Unfinished
records remain waiting or serving under the ended session, preserving their actual history.
Connected pages automatically show the ended state and remove mutation controls.

Cookie expiry is separate from database retention. Names and token hashes are
nullable to support future approved anonymization; no retention/deletion job runs.

## Live updates (Milestone 5)

Start the local server with `python run.py` (optionally `--debug`, `--host`, or
`--port`). It uses Flask-SocketIO's `run()` entry point with threading and the
existing `simple-websocket` dependency. This is a development server, not an Azure
deployment configuration. Run exactly one application worker/process; there is no
Redis, message broker, or queue stored in Python memory.

After a successful Join, Leave, Serve next, Done, or End transaction, the service
emits `queue_changed` with an empty object to that session's student and instructor
rooms. Retries that do not change queue state emit nothing. The notice contains no
names, queue numbers, entry IDs, browser identifiers, credentials, or instructor
data. The browser fetches a fresh server-rendered fragment through its own HTTP
cookies; instructor ownership and student browser identity are checked there on
every request. This also prevents an old instructor socket from exposing private
state after logout. Socket events cannot mutate the queue or choose arbitrary rooms.

- Master state: `GET /instructor/sessions/<public_code>/state` (owner only).
- Client state: `GET /session/<public_code>/state` (only this browser's request).
- Socket transport: `/socket.io`, same origin, CSRF-validated subscription handshake.
- Rooms: `master:<public_code>` for the owner; `session:<public_code>` for guests.

Pages reconcile immediately on connection/reconnection and when returning to a
visible tab. Refreshes are serialized and coalesced to avoid stale responses
overwriting newer state; optional names being typed are preserved. A 30-second
reconciliation also recovers missed notices or temporary socket failures. Failed
broadcasts cannot roll back a committed request. Notifications are best effort,
not a durable event log. Connection status and manual refresh remain available.
Without JavaScript, ordinary forms and manual refresh still work. Exit is passive:
disconnecting never leaves the queue, and the Exit page opens no socket.

The Socket.IO 4.8.1 browser client is vendored locally under `app/static/vendor/`
with its MIT license and source/hash notes. No runtime CDN or Node build is needed;
`requirements.txt` is unchanged. No schema changes or migration are required.
In-browser sound/vibration are available in Phase 7A; Web Push remains deferred.

## Wait-time estimates (Milestone 6)

Waiting students see an approximate wait from `app/services/wait_time.py`'s
`WaitTimeService`. The arithmetic mean of **at least 3 valid current-session
completions** takes priority. Otherwise, use this instructor's completed helps
from **other ended sessions in the last 90 days**, based on completion time. One
historical sample is sufficient; sparse current samples are not mixed in. If
neither source qualifies, show that there is not enough completed help history.

Only completed requests with positive, ordered, non-future service timestamps and
no leave timestamp count. Incomplete, waiting, serving, left, and zero-duration
requests are excluded; historical completions must precede their session's end.
Other instructors' requests never contribute. No outlier trimming is applied.

Multiply the unrounded average by the number ahead, including one full expected
help for whoever is currently serving, then round the **total up to whole minutes**.
Elapsed service time is not subtracted. With nobody ahead, show that the student
is waiting for the instructor instead of promising an immediate start. Estimates
exclude instructor pauses and disappear outside the waiting state. Live updates
and manual refresh recalculate them from SQL Server; nothing derived is stored.

The policy is intentionally fixed and simple in this milestone. See
`docs/architecture.md` for exact boundaries. No migration or dependency changes
are needed. Run `pytest tests/test_wait_time.py` for the focused test suite.

## Student alerts (Phase 7A)

The first waiting request sees **You're next**, even if the instructor has not yet
begun serving. Once service begins it sees **It's your turn**. These are derived
from the authoritative database snapshot, not browser guesses about queue counts.
Static text, icons, and dashed/solid borders convey state without relying on color
or flashing. They also work without JavaScript and under reduced-motion preferences.

After joining, students may select **Enable and test sound** and/or **Enable and
test vibration**. Each can be turned off separately. Sound initializes through this
interaction; blocked or unsupported media shows a message while the visual state
and queue controls remain usable. Enabled effects fire once per request's Next Up
or Serving state on the current page. Repeated updates and reconnects do not replay
alerts. A polite screen-reader announcement and tab title reflect changed state.

Choices last only while participating on that page. Reloading or returning from
Exit requires enabling effects again. Leaving, completing, ending the session,
losing access, or exiting stops effects. Keep the page open: background/sleeping
browsers, device volume, or vibration support may suppress optional effects.
No Web Push, service workers, permission prompts, or subscription records are added.
No location is requested. No schema or dependency changes are required.

Run `pytest tests/test_student_alerts.py tests/test_live_browser.py` for the focused
state, event/privacy, and browser fallback checks. Browser tests use mocked media
APIs in an isolated headless browser; real-device volume/haptics still depend on
the device. They skip if Chrome/Chromium/Edge is not installed.

## Instructor settings (Milestone 8)

Select **Settings** in instructor navigation (`/instructor/settings`). Preferences
apply to that instructor's current and future sessions. Next Up/advance-warning,
Serving, and visual emphasis default to enabled. Sound and vibration default to
allowed, but each student must still enable/test them on their page.

Warning distance accepts **1–3 waiting requests**, default 1; it excludes anyone
serving and historical requests. Only the first waiting request is Next Up. Others
within the configured distance see **Your turn is approaching**. Disabling alerts
preserves ordinary queue status and controls. Live settings changes turn off
disallowed effects without replaying an alert or overriding a student's opt-in.
Push preferences are deferred until Web Push is implemented.

Apply the new migration before running the updated app:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
```

The initial SQL Server baseline includes instructor settings;
registration creates settings for new accounts. One row per instructor and warning
count bounds are enforced by SQL Server. Preferences are included in the initial baseline.
There are no dependency changes. Run the focused persistence, ownership, migration,
and media checks with:

```powershell
pytest tests/test_settings.py tests/test_migrations.py tests/test_live_browser.py
```

## Instructor authentication policy

- Email whitespace is trimmed and the entire address is lowercased, including the
  local part. Internationalized domains are converted to ASCII IDNA form. Unicode
  local parts are rejected. Dots and `+tags` are preserved; they are not aliases.
  Email syntax is checked without DNS/deliverability requests. SQL Server enforces
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
  Client-address forwarding headers are not trusted by default. Production proxy
  configuration must explicitly verify trustworthy hops; otherwise clients behind that proxy
  share its limit. Clients behind the same NAT also share a limit.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required secret for Flask/CSRF. |
| `APP_ENV` | `development` (default) or `production`; production enables strict validation. |
| `TRUSTED_HOSTS` | Required exact comma-separated hostnames in production. |
| `PROXY_FIX_X_FOR` | Trusted client-address proxy hops, 0–3; defaults to 0 pending ingress verification. |
| `DATABASE_URL` | Required for ordinary app instances; SQL Server URL using `mssql+pyodbc`; same credential for startup migrations and runtime. |
| `TEST_DATABASE_URL` | Required for test instances; never falls back to `DATABASE_URL`. |
| `SESSION_COOKIE_SECURE` | `true` for HTTPS cookies; `false` for local HTTP (default). |
| `AUTH_RATE_LIMIT` | Positive integer; shared sign-up/login POST limit per address (default 20). |
| `AUTH_RATE_WINDOW_SECONDS` | Positive integer; fixed rate-limit window (default 900). |
| `STUDENT_COOKIE_MAX_AGE` | Positive cookie lifetime in seconds (default 15552000 / 180 days). |

Only `mssql+pyodbc` and Microsoft ODBC Driver 18 are supported. The URL must include
`driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` in
production, using the canonical Azure SQL hostname. Local self-signed containers
use `TrustServerCertificate=yes`. Unknown/duplicate URL options and extra binds
are rejected; test selection cannot be overridden through SQLAlchemy config.

## Tests and database isolation

The same Linux environment runs locally and in GitHub CI, including on Windows
hosts without ODBC installed:

```powershell
docker compose up -d --wait test-db
docker compose build test-runner
docker compose run --rm test-runner python -m ruff check .
# Provisions only the disposable test database, then runs pytest -m "not browser":
docker compose run --rm test-runner
# Complete pytest, including optional browser checks (skip if browser absent):
docker compose run --rm test-runner python -m pytest
# Optional coverage after test provisioning:
docker compose run --rm test-runner python -m pytest --cov=app --cov-report=term-missing
```

To run pytest in the host virtual environment, install Driver 18, provision the
test database using the command above, and configure `.env` from `.env.example`:

```powershell
ruff check .
pytest -m "not browser"
# Optional manual live browser/DOM tests, using host Chrome/Chromium/Edge:
pytest -m browser
```

`browser` tests cover draft preservation, reconnects, refresh ordering and alert
fallbacks. They are optional/manual and excluded from normal CI and the deployment
gate because hosted Chromium can fail for runner-specific reasons. They skip if
no browser is installed. Plain `pytest` still includes them. Only Linux test
browsers in `CI`/`GITHUB_ACTIONS` use `--no-sandbox`; Windows and normal developer
sandboxing remain unchanged. All unit, database, migration, auth, queue, settings,
Socket.IO and production configuration tests remain required.

Before creating an engine, `TESTING=True` requires `TEST_DATABASE_URL` with a
loopback host, database and user ending in `_test`, and only the validated Driver
18/TLS options. Test and development database names must differ. The fixtures check
actual `DB_NAME()` and `USER_NAME()` before applying Alembic or deleting test rows.
Missing configuration/unavailable SQL fails the suite; tests never silently fall
back to another database. No test uses `create_all()` or `drop_all()`.

| Compose service | Host port | Database / user | Storage |
| --- | --- | --- | --- |
| `db` | 55432 | `takeanumber_dev` | Persistent dedicated SQL Server volume |
| `test-db` | 55433 | `takeanumber_test` | Separate disposable memory filesystem |
| `test-runner` | Shares test-db's loopback network | Test-only credentials | Source mount + Python/ODBC image |

The servers have separate credentials/storage. `scripts/init_test_database.py`
only provisions a guarded, disposable loopback test target, with schema-level
permissions equivalent to production, never database-owner membership. Tests apply
the initial migration, verify model/schema agreement, constraint failures,
transaction rollback, locking, upgrade idempotence and future revisions. Do not
run parallel test processes against this one test database.

## Operations: CI and Azure deployment

The normal release is **CI -> App Service publish-profile deploy -> automatic startup
migration using DATABASE_URL -> Gunicorn**. CI uses its own SQL Server containers,
with no access to the production database. The main-only **Deploy Azure production**
workflow reruns CI, uses the protected `production` environment and deploys tracked
runtime files with `azure/webapps-deploy@v3` and `AZURE_WEBAPP_PUBLISH_PROFILE`.

Use one App Service Linux/Python 3.13 instance, one worker and Azure SQL Database.
The startup command is **`bash startup.sh`**. It validates production configuration,
runs the safe `deploy-upgrade` wrapper and starts Gunicorn only after a successful
migration. Both phases use the **same application user and DATABASE_URL**. No
separate migration credential, Azure CLI login, migration host or manual schema
step is needed for normal releases or initialization of an empty database.

See [the deployment runbook](docs/deployment.md) for exact Portal setup, application
user SQL/grants, connection string, first and future releases, timeout/locking
behavior, diagnostics, rollback limitations and serverless cold-start latency.
[The database port audit](docs/database-port.md) records dialect changes and files.
Azure resources and App Service settings must still be configured; repository
validation does not itself perform a production deployment.

`/health` is liveness-only and never wakes SQL. NullPool plus disabled pyodbc pooling
close idle connections. Only connection opening is retried, never a transaction or
statement. The first request after auto-pause can return a safe 503 while SQL wakes;
active classroom views keep querying SQL and prevent idle auto-pause.

## Migrations

`migrations/versions/0001_sqlserver_baseline.py` initializes the complete current
schema: instructor, instructor_setting, help_session, student_identity and queue_entry.
It preserves UUIDs, timestamp constraints, normalized emails, Unicode names,
filtered uniqueness, authorization ownership and historical queue data. The retired
engine-specific revisions remain in Git history; there is no production data to
convert. This baseline requires a **new empty SQL Server/Azure SQL database**.

For local development only:

```powershell
flask --app app:create_app db upgrade
flask --app app:create_app db current
# After a model change, generate and review a new revision:
flask --app app:create_app db migrate -m "describe the schema change"
```

Production startup always calls `python -m flask --app app:create_app deploy-upgrade`.
Its transaction-owned SQL application lock, bounded timeouts and final-head check
protect migration execution. The application factory does not migrate and no schema
creation shortcut is used. Future migrations extend the baseline; do not edit it
after first deployment. Downgrading the baseline deletes application tables/data
and is tested only on the disposable test database. Routine deployments require
backward-compatible, transactional changes; never auto-downgrade a failed release.

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
  realtime.py      Socket.IO room subscriptions and post-commit notices
  cli.py           database check and serialized deployment migrations
  health/          health blueprint
  models/          Instructor, HelpSession, StudentIdentity, QueueEntry
  auth/            forms, credential services, routes, authentication throttling
  instructor/      dashboard and session management blueprint
  queue/           public Client View, browser cookie, and forms
  services/        session/queue transitions, private state, browser identity
  templates/       server-rendered instructor and student views
  static/          focused live-update JavaScript and vendored Socket.IO client
run.py             local single-process Socket.IO server
startup.sh         production single-worker threaded Gunicorn startup
.github/workflows/ SQL Server CI and protected Azure publish-profile deployment
migrations/        Alembic configuration and versioned schema
tests/             foundation, authentication, session, database, and migration tests
compose.yaml       local development and test SQL Server servers
pyproject.toml     pytest and Ruff settings
```
