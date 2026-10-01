# Take A Number

A Flask/PostgreSQL application for student help queues in college labs.
Milestones 0–6, Phase 7A, and Milestone 8 provide the Flask/PostgreSQL foundation, instructor authentication,
help sessions, public student queue joining/leaving, Master View advancement, and
live queue updates, wait-time estimates, in-browser student alerts, and instructor settings.
See `docs/implementation-plan.md` for later milestones.

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
python run.py --debug
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

A PostgreSQL partial unique index permits only one active session per instructor.
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

Join, Leave, Serve next, Done, and End share a session row lock. PostgreSQL also
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
and port. Reverse-proxy URL handling remains part of future deployment work.

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
creation commit together. PostgreSQL independently enforces unique session numbers
and one waiting/serving entry per browser identity per session using an explicit
partial unique index. Duplicate joins return the existing request unchanged.
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
and manual refresh recalculate them from PostgreSQL; nothing derived is stored.

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

Migration `0005_instructor_settings` backfills existing instructors with defaults;
registration creates settings for new accounts. One row per instructor and warning
count bounds are enforced by PostgreSQL. Downgrading removes preferences only.
There are no dependency changes. Run the focused persistence, ownership, migration,
and media checks with:

```powershell
pytest tests/test_settings.py tests/test_migrations.py tests/test_live_browser.py
```

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
| `STUDENT_COOKIE_MAX_AGE` | Positive cookie lifetime in seconds (default 15552000 / 180 days). |

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

Socket.IO tests cover room isolation, ownership, CSRF/origin rejection, minimal
payloads, commit-before-notify, rollback, reconnects, and private state responses.
If Chrome, Chromium, or Edge is installed, pytest also runs an isolated headless
DOM test for draft preservation, reconnects, and overlapping refreshes. That one
optional test skips when no supported browser is available.

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

Integration tests verify the actual database and role, apply Alembic migrations
only to the dedicated test database, and clean queue entries, browser identities,
help sessions, then instructors between tests. Migration tests downgrade to base or the previous milestone
and upgrade again on that disposable database, including preservation of existing
instructor accounts across the HelpSession migration.
Tests do not call `create_all` or `drop_all`. Do not run parallel test processes
against this single test database.

## Migrations

`migrations/versions/0001_instructor_create_instructor.py` creates only `instructor`:
UUID primary key, normalized unique email, required display name/hash, active flag,
and UTC-aware creation/update timestamps. ORM updates refresh `updated_at`.

`migrations/versions/0002_help_session_create_help_session.py` adds `help_session`
with its instructor foreign key, unique public code, one-active-session index,
and status/timestamp/counter constraints. Apply it using `db upgrade` before
opening the dashboard after updating from Milestone 1.

`migrations/versions/0003_student_queue_create_student_identity_and_queue_entry.py`
adds browser identities and historical queue entries, including the explicit
active-entry partial unique index. Run `db upgrade` before opening the Client View.

`migrations/versions/0004_queue_advancement_one_serving_per_session.py` adds the
partial unique index allowing only one serving entry per session. Run `db upgrade`
before using the Milestone 4 Master View. Its downgrade removes only that index,
preserving all requests and timestamps. Existing invalid multiple-serving data
causes upgrade to fail rather than silently rewriting history.

```powershell
flask --app app:create_app db upgrade
flask --app app:create_app db current
# After a future model change, generate and review the migration before upgrading:
flask --app app:create_app db migrate -m "describe the schema change"
```

The initial migration's downgrade removes the instructor table and its account
data. Downgrading Milestone 2 to Milestone 1 removes session records but preserves
instructors. Downgrading Milestone 3 removes queue entries and browser identities
but preserves sessions/instructors and their existing queue-number counters.
Automated downgrade tests run only on the dedicated test database.

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
  cli.py           read-only database check
  health/          health blueprint
  models/          Instructor, HelpSession, StudentIdentity, QueueEntry
  auth/            forms, credential services, routes, authentication throttling
  instructor/      dashboard and session management blueprint
  queue/           public Client View, browser cookie, and forms
  services/        session/queue transitions, private state, browser identity
  templates/       server-rendered instructor and student views
  static/          focused live-update JavaScript and vendored Socket.IO client
run.py             local single-process Socket.IO server
migrations/        Alembic configuration and versioned schema
tests/             foundation, authentication, session, database, and migration tests
compose.yaml       local development and test PostgreSQL servers
pyproject.toml     pytest and Ruff settings
```
