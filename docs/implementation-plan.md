# Take A Number — Implementation Plan

This plan intentionally breaks development into reviewable Codex-sized milestones.

Do not ask Codex to build the entire application in one task.

## Milestone 0 — Repository foundation

Goal: establish a clean Flask/PostgreSQL project skeleton.

Deliverables:

- application factory
- extension initialization
- config classes/environment handling
- health endpoint
- initial package structure
- `.env.example`
- `.gitignore` updates as needed
- Docker Compose PostgreSQL development service
- dedicated PostgreSQL test database strategy
- pytest configuration
- basic smoke test
- Ruff configuration if not already present
- README bootstrap instructions

Acceptance criteria:

- app starts locally
- app connects to PostgreSQL
- tests connect only to test database
- `ruff check .` passes
- `pytest` passes

No authentication or queue logic yet.

## Milestone 1 — Instructor authentication

Goal: instructor account lifecycle.

Deliverables:

- Instructor model
- migration
- sign-up
- login
- logout
- Flask-Login integration
- authenticated dashboard placeholder
- authorization tests
- password hashing tests/behavior

Acceptance criteria:

- unique email enforced
- passwords never stored plaintext
- unauthenticated dashboard access redirects appropriately
- tests pass

## Milestone 2 — Help sessions

Goal: authenticated instructors can start/manage their own session.

Deliverables:

- HelpSession model
- migration
- unique public code
- start session action
- active session display
- ownership enforcement
- end session action
- tests

Acceptance criteria:

- instructor cannot control another instructor's session
- ended session rejects queue joins
- public code does not expose DB primary key

## Milestone 3 — Student identity and joining

Goal: guest student can join with minimal friction.

Deliverables:

- StudentIdentity model
- QueueEntry model
- migration
- browser pseudonymous identity mechanism
- Client View
- Take A Number
- optional name
- duplicate prevention
- queue position calculation
- Leave Queue
- Exit passive behavior
- tests

Acceptance criteria:

- no login required
- no location requested or stored
- refresh preserves active queue state where browser identity persists
- repeated requests cannot create duplicate active entries

## Milestone 4 — Queue advancement and Master View

Goal: complete the core instructor workflow.

Deliverables:

- Master View
- currently serving
- next up
- truncated queue
- waiting count
- Done
- queue advancement service
- QR code to Client View
- edge-case tests

Acceptance criteria:

- transitions are transactional
- correct timestamps are recorded
- empty queue is handled safely
- multiple Master Views read the same authoritative state

## Milestone 5 — Real-time updates

Goal: remove manual refresh.

Deliverables:

- Flask-SocketIO integration
- session rooms
- queue update events
- Master View live updates
- Client View live updates
- targeted state updates as appropriate
- Socket.IO tests where practical

Acceptance criteria:

- join/leave/done/end updates propagate
- server/database remains authoritative
- no Redis
- single-worker assumption documented

## Milestone 6 — Wait-time estimation

Goal: show useful estimated waits.

Deliverables:

- WaitTimeService
- current-session average help time
- historical instructor fallback
- estimated wait shown in Client View
- tests for no-history, sparse-history, and normal cases

Acceptance criteria:

- calculation is deterministic and tested
- missing data yields sensible UI rather than errors

## Milestone 7 — Student alerts

Goal: restaurant-pager-like experience.

Phase 7A:

- Next Up visual state
- Currently Serving visual state
- sound
- vibration where supported
- capability-aware fallbacks

Phase 7B:

- service worker
- push permission explanation
- push subscriptions
- secure subscription persistence
- Web Push delivery

Acceptance criteria:

- denial/unsupported APIs do not break queue use
- sound/vibration triggered only in browser-appropriate ways
- alerts correspond to server state transitions

## Milestone 8 — Instructor settings

Goal: configurable alert preferences.

Deliverables:

- InstructorSetting model
- migration
- settings page
- alert toggles
- warning distance
- tests

## Milestone 9 — Metrics

Goal: historical instructor analytics.

Deliverables:

- MetricsService
- session summary
- date-range metrics
- help frequency by pseudonymous browser identity
- help frequency by optional entered name
- clear wording around identity limitations
- tests

Metrics:

- helps/session
- total helps
- average/median/longest help
- average/longest wait
- session duration
- peak queue length
- frequent help-requesting browser identities
- frequent entered names

## Milestone 10 — CI/CD and Azure

Goal: repeatable deployment.

Deliverables:

- GitHub Actions test workflow
- PostgreSQL service in CI
- Ruff + pytest gates
- Azure deployment workflow
- OIDC Azure authentication
- Azure App Service startup command
- production config
- migration/deployment procedure
- Application Insights/logging review

Acceptance criteria:

- PR checks run automatically
- main deployment is controlled and reproducible
- no long-lived Azure password is required in GitHub if OIDC is available
- production secrets are outside source control
