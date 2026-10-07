# AGENTS.md — Take A Number

## Project purpose

Take A Number is a multi-instructor web application for managing student help queues during college computer labs.

Instructors authenticate, start and manage help sessions, and use a Master View on a podium display and/or mobile device. Students join a session without creating an account, normally by scanning a QR code, and use a Client View to take a number, see their queue position and estimated wait, leave the queue, and receive alerts when they are next or currently being served.

## Technology baseline

- Python
- Flask
- SQL Server only
- Flask-SQLAlchemy
- Flask-Migrate / Alembic
- Flask-Login
- Flask-WTF
- Flask-SocketIO
- `simple-websocket`
- `pyodbc` (Microsoft ODBC Driver 18)
- `python-dotenv`
- `qrcode`
- Gunicorn for production
- pytest
- pytest-cov
- Ruff
- GitHub
- GitHub Actions
- Azure App Service
- Azure SQL Database

Do not add SQLite compatibility.

## Architectural rules

1. Use the Flask application factory pattern.
2. Organize major features as Flask blueprints.
3. Keep route handlers thin.
4. Put queue transitions, wait-time calculations, metrics, and other business rules in service modules.
5. Keep persistence logic in models/repositories/services rather than embedding complex queries in templates.
6. Use database constraints in addition to application validation where appropriate.
7. Every schema change requires a Flask-Migrate/Alembic migration.
8. Never manually create production application tables outside migrations.
   Production startup must run `deploy-upgrade` successfully before Gunicorn;
   the factory never migrates and `db.create_all()` is not a deployment mechanism.
9. Public identifiers must not expose sequential database primary keys.
10. Prefer UUID primary keys for internal records and separate human-friendly queue numbers/session codes for display.
11. Build real-time UI updates around server-authoritative state.
12. Queue state transitions must be atomic.
13. Do not introduce Redis or a multi-worker Socket.IO design until explicitly requested. Initial deployment assumes one application worker.
14. Do not introduce a JavaScript SPA framework unless explicitly requested. Prefer server-rendered Flask templates plus focused JavaScript.

## Security rules

1. Never store plaintext passwords.
2. Use Flask-Login for instructor sessions.
3. Use CSRF protection for state-changing form requests.
4. Keep secrets and credentials out of source control.
5. Configuration comes from environment variables.
6. Do not log passwords, authentication tokens, notification subscription secrets, or raw session cookies.
7. Apply authorization checks to all instructor/session management actions.
8. An instructor may manage only sessions they own unless an administrator feature is explicitly added later.
9. Student participation must not require authentication.
10. Rate-limit or otherwise protect authentication endpoints when that feature is implemented.

## Student privacy rules

1. Do not collect student location.
2. Do not ask students for seat, workstation, room position, GPS location, or similar location information.
3. Student accounts are not required.
4. Generate a random pseudonymous browser identifier for a student device/browser profile.
5. Treat a pseudonymous browser identifier as a browser/device signal, not proof of a person's identity.
6. Student-entered names are optional unless requirements explicitly change.
7. Metrics may use pseudonymous browser identifiers and optional entered names, but documentation/UI must not imply that a browser identifier definitively represents one student.
8. Design retention so pseudonymous identifiers and student-entered names can later be expired according to configurable policy.
9. Collect no additional personal data unless required by an approved feature.

## Queue rules

1. A student may have at most one active queue entry per session for the same browser identity.
2. Repeated button presses must not create duplicate active entries.
3. Refreshing the Client View must preserve the student's active queue state when the browser identifier remains available.
4. Leaving the queue removes the active request but does not corrupt historical metrics.
5. "Exit" from the Client View must not implicitly remove the student from the queue.
6. Queue numbers are human-friendly sequence numbers scoped to a session.
7. Pressing Done must complete the currently served entry and advance the queue consistently.
8. Ending a session must mark the session ended, stop new joins, and notify connected clients.
9. Multiple Master View browsers for the same instructor session must remain synchronized.
10. All queue mutations require automated tests.

## Alerting rules

The Client View should support progressively enhanced alerts:

- visual state change / flashing
- sound
- vibration where supported
- browser push notifications when implemented and permission is granted

Do not assume vibration or push notifications are universally supported.

The application must remain usable when notifications are denied or unsupported.

## Metrics rules

At minimum, preserve data required to calculate:

- help duration
- wait duration
- average help duration
- median help duration
- average wait duration
- longest help duration
- longest wait duration
- helps per session
- total helps over a selected time period
- peak queue length
- help-request frequency by pseudonymous browser identity
- help-request frequency by optional entered student name
- instructor-specific historical metrics

Do not store derived values unnecessarily when they can be calculated reliably from timestamps.

## Testing expectations

- Use pytest.
- Tests use a dedicated SQL Server test database.
- Never run tests against the development or production database.
- Add tests for all queue state transitions.
- Add tests for ownership/authorization boundaries.
- Add tests for duplicate joins and idempotent behavior where applicable.
- Add tests for wait-time calculations.
- Add tests for session ending behavior.
- Add tests for student identity persistence behavior.
- Run Ruff and pytest before considering a coding task complete.

## Change discipline

When completing a task:

1. Read the relevant files in `docs/`.
2. Make the smallest coherent change.
3. Add or update tests.
4. Add a migration if the schema changes.
5. Run:
   - `ruff check .`
   - `pytest`
6. Report:
   - what changed
   - migration names, if any
   - tests added/updated
   - commands run and results
   - any unresolved risks or assumptions

Do not silently expand scope.

## Source of truth

For product behavior, use these documents in order:

1. `docs/requirements.md`
2. `docs/architecture.md`
3. `docs/data-model.md`
4. `docs/implementation-plan.md`

If they conflict, stop and report the conflict rather than guessing.
