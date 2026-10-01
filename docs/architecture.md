# Take A Number — Architecture

## 1. Architectural goals

The architecture should be:

- simple enough for one Flask application
- easy for Codex and human maintainers to navigate
- safe for multi-instructor use
- real-time for queue state
- PostgreSQL-first
- deployable to Azure App Service
- testable without browser automation for core business rules
- extensible for analytics and notifications

## 2. High-level architecture

```text
Student Browsers                  Instructor Browsers
(Client View)                     (Master View / Dashboard)
       |                                  |
       | HTTPS / Socket.IO                | HTTPS / Socket.IO
       +------------------+---------------+
                          |
                    Flask Application
                          |
        +-----------------+------------------+
        |                 |                  |
      Auth             Queue             Metrics
    Blueprint         Services            Services
        |                 |                  |
        +-----------------+------------------+
                          |
                    SQLAlchemy ORM
                          |
                     PostgreSQL
```

Production:

```text
GitHub
  |
  | GitHub Actions
  v
Azure App Service
  |
  v
Azure Database for PostgreSQL Flexible Server
```

## 3. Flask application structure

Recommended structure:

```text
app/
  __init__.py
  config.py
  extensions.py
  models/
  auth/
  instructor/
  queue/
  metrics/
  notifications/
  templates/
  static/
tests/
migrations/
docs/
```

A package-per-model or single `models.py` are both acceptable initially. Prefer the least complex structure that remains readable.

## 4. Application factory

The application must use an application factory:

```python
def create_app(config=None):
    ...
```

Responsibilities:

- load configuration
- initialize extensions
- register blueprints
- register error handlers
- register Socket.IO handlers
- configure logging

Avoid import cycles by keeping extension objects in `app/extensions.py`.

## 5. Suggested extensions

`app/extensions.py` may expose:

- `db`
- `migrate`
- `login_manager`
- `csrf`
- `socketio`

Do not initialize them with an app at import time.

## 6. Blueprints

### auth

Responsibilities:

- sign-up
- login
- logout

### instructor

Responsibilities:

- dashboard
- create/end sessions
- Master View
- settings
- historical session views

### queue

Responsibilities:

- public Client View
- join queue
- leave queue
- restore current client state
- instructor queue mutations via service calls
- queue-related Socket.IO events

### metrics

Responsibilities:

- historical analytics UI/API
- metric queries/aggregation

### notifications

May begin as service modules rather than a blueprint.

Responsibilities:

- determine alert transitions
- browser push subscription persistence later
- alert event payloads
- notification capability checks/integration boundaries

## 7. Service layer

Business logic must not live primarily in routes.

Suggested services:

```text
SessionService
QueueService
WaitTimeService
MetricsService
StudentIdentityService
NotificationService
```

### QueueService

Owns state transitions such as:

- join queue
- leave queue
- begin serving
- complete current
- advance queue
- end-session queue handling

All queue-changing operations should be transaction-safe.

### WaitTimeService

Owns:

- current-session average help duration
- fallback to instructor history
- estimated wait calculation

Milestone 6 policy (defined before implementation):

- Use the arithmetic mean of valid completed help durations in the current
  session once it has at least **3** valid completions.
- Below 3, use all valid completed helps from this instructor's **other, ended
  sessions**, completed within the preceding **90 days**, inclusive of the cutoff.
  One historical completion is sufficient. Do not blend histories or reuse the
  sparse current sample as a third fallback. With no qualifying history, return
  unavailable. Historical sessions must have ended by the calculation time.
- A valid row has status `completed`, non-null join/start/completion timestamps,
  `service_started_at >= joined_at`, `completed_at > service_started_at`, no
  `left_at`, and completion no later than the calculation time. Historical
  completion must also be no later than its session's end. Waiting, serving,
  left, incomplete, zero/negative-duration, and future completions are excluded.
  Do not trim legitimate long durations or add smoothing in this milestone.
- Multiply the unrounded mean duration by the number ahead. A currently serving
  request ahead counts as one full expected help, just like a waiting request.
  Do not subtract elapsed service time or run a countdown. Queue numbers identify
  order; gaps from left/completed requests do not count as people ahead.
- Round only the final product **up to whole minutes**. Show `About N minutes`
  (singular for 1). With people ahead but no usable history, show `Not enough
  completed help history yet`. Zero people ahead returns 0 without needing
  history; the UI instead says `No one ahead; waiting for the instructor` because
  Serve next remains explicit. Hide estimates once serving, left, completed, or
  ended, and before joining. Estimates exclude instructor pauses and are not a
  promise about the exact start time.
- `WaitTimeService` is a dedicated read-only service. It accepts an explicit UTC
  calculation time for deterministic tests; ordinary calls use PostgreSQL wall
  time. Client snapshots calculate the estimate while retaining their existing
  session lock. No derived duration/estimate is stored, and no schema change is
  required. Existing live fragment refreshes recalculate the estimate.

### MetricsService

Owns:

- session aggregates
- time-range aggregates
- help-frequency queries

### StudentIdentityService

Owns:

- creation/validation of pseudonymous browser identity
- restoration of active queue state

## 8. State model

Recommended queue entry statuses:

```text
waiting
serving
completed
left
cancelled_by_session_end   # optional; evaluate before implementation
```

Do not over-model states prematurely. If session-end cancellation is not analytically useful, waiting entries may remain `waiting` with the ended session indicating they were never served, or use an explicit terminal status. Decide before schema migration and document the choice.

Unfinished entries retain their `waiting` or `serving` state when a session ends;
the parent session's ended state closes participation. No cancellation status or
synthetic completion/leave timestamp is added. Every new join initially waits;
Milestone 4 explicitly begins service with Serve next when nobody is serving.
Done completes the displayed serving request and starts the first waiting one
atomically, or leaves the queue idle if nobody is waiting. Done without a matching
serving request is a no-op. If a serving request leaves, the next request waits for
Serve next. No synthetic completion is recorded when a session ends.

`app/services/queue.py` is the QueueService module. Advancement checks ownership,
locks the session row before querying entries, and commits completion and promotion
together. Both Serve next and Done carry the displayed entry UUID; stale or repeated
forms cannot act on its successor. A partial unique index independently restricts
each session to one serving entry. Completion is flushed before promotion to release
that index slot, with both writes still in the same transaction. One database wall
timestamp, obtained after acquiring the lock, records completion and the next start.

Master View reads use a shared session lock to capture a consistent, ownership-scoped
snapshot: serving, the first five waiting requests, and the full waiting count.
Snapshots contain numbers and optional names, never browser tokens or hashes.
Milestone 5 refreshes these snapshots after socket notices. QR images are generated locally as SVG by the existing
`qrcode` dependency; the encoded URL is Flask's external public Client View URL for
the requested session. The QR endpoint requires the owner and an active session.

Recommended session statuses:

```text
active
ended
```

## 9. Real-time model

The database is authoritative.

Socket.IO broadcasts should be emitted after successful database commits.

Milestone 5 room structure:

```text
session:{public_code}   # guest Client Views; notice only
master:{public_code}    # authenticated owner; notice only
```

At minimum, joining a public session room allows queue updates to be broadcast efficiently.

Do not rely on in-memory Python state for the queue.

Each factory creates an independent Socket.IO server, stored in
`app.extensions['socketio']`, using threading and same-origin transport defaults.
The connection handshake validates CSRF explicitly (Flask before-request hooks do
not run for sockets), validates the public code, and checks ownership for a Master
View. Connections subscribe to exactly one server-chosen room. There are no room
switching, queue mutation, or arbitrary relay event handlers.

Join, Leave, Serve next, Done, and End call `publish_queue_changed` only after a
successful commit, and only for actual queue transitions. The emitted
`queue_changed` payload is `{}`. It carries no private data, not even an entry ID.
All clients in that session reconcile by fetching their view's HTML fragment over
HTTP with current cookies. Master fragments recheck Flask-Login and ownership;
Client fragments resolve only the signed browser cookie. Cookie scope stays
`/session`; it is neither needed nor sent to the default `/socket.io` path. No
browser token is copied into socket auth or JavaScript. Templates escape names.
HTTP fragments are never cached. Existing socket membership after logout cannot
reveal instructor data because the subsequent HTTP read is unauthorized.

State reads retain the existing shared session lock and return consistent database
snapshots. The browser serializes fetches, coalesces notices during a pending read,
and discards a superseded response. There is no client-side authoritative queue or
socket snapshot ordering problem. Connection/reconnection, tab visibility, and a
30-second reconciliation trigger fresh reads. Optional name drafts survive updates.
Authorization/cookie errors clear the stale view and stop updates. HTTP actions
remain CSRF-protected and work without JavaScript. Exit opens no socket and closing
or losing a socket never mutates participation.

Broadcast failures are logged without sensitive exception contents and never
change an already committed result. Notices are best effort: periodic reads and
reconnects recover failures or the commit-to-broadcast process-crash window. A
durable outbox/event log is not part of this milestone. No schema change is needed.

The browser client is pinned and served locally, avoiding runtime third-party
requests. See `app/static/vendor/README.md` for provenance and license.

## 10. Initial worker model

Initial production deployment assumes:

- one Gunicorn worker/application process
- Socket.IO supported through `simple-websocket`
- no Redis/message broker

If horizontal scaling or multiple workers are later required, introduce:

- a compatible message broker (likely Redis)
- sticky-session/load-balancing review
- updated deployment architecture

Do not add this complexity before it is needed.

## 11. Configuration

Use environment variables.

Suggested keys:

```text
SECRET_KEY
DATABASE_URL
FLASK_ENV
APP_BASE_URL
SESSION_COOKIE_SECURE
```

Later:

```text
VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY
VAPID_SUBJECT
```

Do not commit `.env`.

Commit `.env.example`.

## 12. PostgreSQL

PostgreSQL is the only supported database.

Development should also use PostgreSQL.

Recommended local development:

- PostgreSQL in Docker
- Flask in local `.venv`

Use a separate PostgreSQL database for tests.

## 13. Migrations

All schema changes use Flask-Migrate/Alembic.

A schema-changing Codex task is incomplete unless:

- models are updated
- migration is generated and reviewed
- tests are updated
- migration can upgrade from the previous schema
- migration downgrade is reasonable where practical

## 14. Public identifiers

Do not expose integer database IDs in public URLs.

Use:

- UUIDs internally where convenient
- a random/opaque public session identifier or short public join code for sessions
- session-scoped sequential queue numbers for humans

Example:

```text
/session/7QKF9M/join
/session/7QKF9M/master
```

The public code is not an authorization mechanism for instructor controls.

## 15. Student browser identity

Generate a high-entropy random identifier in the browser or server-assisted first visit and persist it.

Possible storage:

- secure/signed cookie where practical
- localStorage for a non-secret generated identifier
- combination if justified

This identifier:

- is pseudonymous
- may survive refreshes
- may survive browser restarts depending on storage
- is not proof of a human identity
- may be cleared or changed by the user

Never use browser fingerprinting techniques.

Milestone 3 uses a signed HttpOnly `tan_browser` cookie scoped to `/session`,
containing a random 256-bit token. Only its SHA-256 hash is persisted, and the
identity row is created on a successful join. The cookie is independent of the
instructor authentication session, with SameSite=Lax and the configured Secure
flag. Its configurable default lifetime is 180 days and renews on Client View GET.

Forms bind to the browser cookie that rendered them; a missing, invalid, expired,
or changed cookie cannot silently create an identity on POST. The user must reopen
the Client View. Simultaneous first page loads before any cookie is established
can generate different tokens; stale forms are rejected rather than joined under
the wrong token. Clearing cookies or using another browser can still create a new
profile, and shared browsers share a profile. Optional names never merge profiles.

Queue services lock the session before identity/entry writes, using the same lock
as End Session. A join allocates its number and inserts its entry in one transaction;
duplicate joins return the existing active entry without changing its name or
number. Leave targets the rendered entry UUID as well as session and browser hash.
Client snapshots use a shared session lock to read a consistent position and never
expose another browser's records. Exit performs only this read.

## 16. Authentication and authorization

Instructor passwords must be securely hashed.

Use Flask-Login.

Every instructor mutation checks ownership.

Public student routes may access only public session state required for queue participation.

Never allow a public session code alone to authorize instructor actions.

## 17. Notification architecture

### Phase 1

Implement:

- visual alert state
- sound initiated after user interaction
- vibration when supported

Phase 7A implementation derives `ClientState.alert_state` inside the existing
shared session lock. A serving entry yields `serving`; the first waiting entry
(no lower-numbered waiting entries) yields `next_up`. Other states yield no alert,
including unfinished entries under an ended session. Next Up is presentation
state, not a new stored queue status. There is no migration.

Socket payloads remain empty invalidation notices, sent after commit. Authorized
HTTP fragments carry only the requesting browser's entry ID, participation state,
and alert state. The live-update script notifies the student alert script only
after applying a fresh fragment; the browser does not infer Next Up from counts
or react to raw socket payloads. The alert script tracks the current request and
already-observed alert kinds in page memory to suppress duplicate effects.

Server-rendered static text, icons, and contrasting border styles supply visual
alerts without movement/flashing, including under reduced-motion preferences.
A persistent polite live region announces changes without moving focus. Optional
sound and vibration each require an enable/test gesture; defaults are off and no
preferences are persisted. Audio resume rejection, suspended contexts, missing
APIs, vibration failure, and teardown are handled without breaking queue controls.
No automatic audio-resume attempts occur during queue refresh. The current state
is reconciled after reconnect, without replaying missed transitions.

Implementation API references: [AudioContext.resume](https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume)
and [Navigator.vibrate](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/vibrate).

### Phase 2

Add Web Push:

```text
Client grants permission
       |
Service worker subscribes
       |
Subscription stored server-side
       |
NotificationService triggers push
```

Push notification design must be optional and must degrade gracefully.

### Instructor alert policy (Milestone 8)

The instructor blueprint serves a login-required, CSRF-protected settings form at
`/instructor/settings`. The owner always comes from `current_user.id`; no route or
form field selects another instructor. `app/services/settings.py` reads immutable
`AlertPreferences` snapshots and atomically saves the complete preference set.
Registration creates a settings row and migration `0005_instructor_settings`
backfills existing accounts. Unique/FK/range constraints enforce persistence rules.

Defaults preserve Phase 7A: Next Up, Serving, and visual emphasis enabled; optional
sound and vibration allowed but off in each student browser until that student
enables them. No push setting or delivery is added. Client snapshots read the
session owner's current policy, so it applies to current and future sessions.
After a settings commit, empty invalidations notify only the owner's active
session rooms. Existing periodic/reconnect reads recover missed notices.

Warning distance is the first **1–3 waiting requests**, default 1, excluding the
serving request and left/completed entries. The first waiting request remains
`next_up` regardless of settings. Additional waiting requests within the distance
have presentation state `advance_warning` and see “Your turn is approaching.”
Both warning kinds obey `alert_next_enabled`; serving obeys its separate toggle.
This never changes stored queue states, ordering, advancement, or wait estimates.

Event toggles gate effects; the visual toggle gates border/background emphasis,
tab titles, and alert announcements. Plain queue status and controls remain visible
with every toggle off. Sound/vibration settings only allow each browser's own
enable/test choice. A live disabling change stops the corresponding effect; a
reenabling change does not opt the student back in. Changes to the policy cancel
pending audio initialization and establish a baseline without replaying effects.
Each new advance-warning, Next Up, or Serving state can signal once per request
on that page. Basic text remains usable without JavaScript or supported media.

## 18. Metrics architecture

Prefer deriving metrics from event timestamps and queue-entry state rather than storing duplicate aggregate values.

Potential timestamps:

- session.started_at
- session.ended_at
- queue_entry.joined_at
- queue_entry.service_started_at
- queue_entry.completed_at
- queue_entry.left_at

A small number of denormalized counters may later be justified for performance, but not initially.

Peak queue length may be derived from event history or captured using a session metric/event mechanism. The initial implementation plan should choose one explicit strategy before implementing this metric.

## 19. Testing strategy

### Unit tests

- wait-time calculations
- metric calculations
- helper functions

### Service/integration tests

Using PostgreSQL test database:

- instructor registration/login
- session ownership
- start/end session
- join queue
- duplicate join protection
- leave queue
- queue advancement
- completion timestamps
- empty queue behavior
- session-ended behavior

### Socket.IO tests

Use Flask-SocketIO test clients where useful to verify emitted events without full browser automation.

### Browser/E2E

Not required for initial milestones unless a behavior cannot be validated adequately otherwise.

## 20. CI/CD direction

GitHub Actions should eventually:

1. install Python dependencies
2. start/provision PostgreSQL service
3. run Ruff
4. run pytest
5. on approved main-branch deployment, authenticate to Azure
6. deploy App Service artifact

Prefer OIDC-based Azure authentication when CI/CD is implemented.
