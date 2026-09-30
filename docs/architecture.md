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

Recommended session statuses:

```text
active
ended
```

## 9. Real-time model

The database is authoritative.

Socket.IO broadcasts should be emitted after successful database commits.

Suggested room structure:

```text
session:{public_session_id}
master:{session_id}     # optional
client:{queue_entry_id} # optional for targeted alerts
```

At minimum, joining a public session room allows queue updates to be broadcast efficiently.

Do not rely on in-memory Python state for the queue.

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
