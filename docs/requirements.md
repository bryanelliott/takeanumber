# Take A Number — Software Requirements

## 1. Purpose

Take A Number is a web-based queue-management application for college computer labs.

The application allows an instructor to run a live help queue while students join with minimal friction. Instructors authenticate; students do not.

## 2. Primary actors

### Instructor

An authenticated faculty member who can:

- create an account
- log in and log out
- start a help session
- display and control a Master View
- open the same Master View on multiple devices
- advance the queue
- end a session
- configure instructor preferences
- review historical metrics

### Student

A guest user who can:

- enter a live help session from a QR code or direct URL
- optionally enter a name
- take a number
- view their queue number
- view the number of people ahead
- view an estimated wait time
- leave the queue
- exit the active interface without losing their queue position
- receive alerts when they are next or currently being served

Students must not be required to create an account or log in.

## 3. Instructor account requirements

The system shall provide:

- instructor sign-up
- instructor login
- instructor logout
- secure password hashing
- authenticated instructor dashboard
- ownership enforcement so one instructor cannot control another instructor's sessions
- an instructor settings page

Potential future authentication integrations, such as institutional Microsoft sign-in, are out of scope for the initial implementation unless explicitly added later.

## 4. Instructor dashboard

The dashboard should provide:

- ability to start a new help session
- visibility of an active session
- access to previous sessions
- access to metrics
- access to instructor settings

An instructor should not accidentally create multiple active sessions unless that behavior is intentionally added later.

## 5. Help session

Each help session must:

- belong to one instructor
- have a unique public session code or token
- have a start timestamp
- have an optional end timestamp
- have a status such as active/ended
- maintain an ordered queue
- maintain a currently served student, if any
- support multiple connected Master Views
- support multiple connected Client Views
- reject new queue joins after the session ends

## 6. Master View

The Master View is intended for a podium display/projector and optionally an instructor mobile device.

It shall display at minimum:

- currently serving
- next up
- a truncated queue
- total number waiting
- a prominent QR code linking to that session's Client View
- Done control
- End Session control

The Master View should update in real time.

Multiple Master Views connected to the same session must remain synchronized.

### Done behavior

When the instructor presses Done:

1. the currently served queue entry is marked completed
2. completion time is recorded
3. the next waiting student becomes currently served
4. the following waiting student becomes next up
5. all connected clients receive updated queue state
6. alerts are triggered as appropriate
7. estimated waits are recalculated

The implementation must define behavior when there is no currently served student or no waiting student and test those cases.

### End Session behavior

When the instructor ends a session:

- the session is marked ended
- ended time is recorded
- new joins are blocked
- connected Master Views update
- connected Client Views receive a session-ended state/message
- historical data is preserved

## 7. Client View

The Client View is intended for mobile browsers.

Before joining, it shall prominently provide a Take A Number action.

After joining, it shall display at minimum:

- the student's queue number
- people ahead
- estimated wait time
- current queue state
- Leave Queue control
- Exit control

### Leave Queue

Leave Queue removes the active request from the queue while preserving historical data needed for analytics.

### Exit

Exit must not implicitly remove the student from the queue.

Because browsers cannot reliably close arbitrary tabs, Exit may navigate to a passive/closed state rather than physically closing the browser tab.

## 8. Student identity

The system must avoid mandatory student accounts.

The system shall generate a random pseudonymous browser identifier and persist it in the student's browser using an appropriate browser storage mechanism.

The system may associate the queue entry with:

- pseudonymous browser identifier
- optional student-entered name

The system must not claim that a browser identifier definitively identifies one human student.

The system must not collect or request student location, seat position, workstation number, room location, GPS location, or similar information.

## 9. Duplicate prevention

Within a session, a given browser identity must not be able to create multiple active queue entries by:

- repeated clicking
- refresh/reload
- repeated API submission

Duplicate prevention should be enforced both in application logic and, where practical, by database constraints.

## 10. Alerts and notifications

The application should alert students when:

- they become Next Up
- they become Currently Serving

Alert methods should include, where supported:

- strong visual state change
- flashing or animated screen
- sound
- vibration
- browser push notification

The application must function when any or all optional alert APIs are unavailable or permission is denied.

The UI should explain notification permission before requesting it.

## 11. Estimated wait time

Estimated wait should primarily use help durations from completed students in the current session.

A reasonable initial approach:

- average completed help duration in current session × number of students ahead

If there are too few completed helps in the current session, the service may fall back to instructor historical averages.

The calculation must be implemented in a service layer and covered by tests.

Exact fallback thresholds and smoothing algorithms can be refined later.

## 12. Metrics

The system shall retain the timestamps and state necessary to calculate at least:

### Per session

- number of students helped
- average help duration
- median help duration
- longest help duration
- average wait duration
- longest wait duration
- session duration
- peak queue length

### Over a selected time range

- total helps
- average help duration
- average wait duration
- helps per session
- number of sessions
- help-request frequency by pseudonymous browser identity
- help-request frequency by optional entered name

### Instructor scope

Initial analytics are instructor-specific. Cross-instructor/administrator analytics are future scope unless explicitly added.

## 13. Instructor settings

Initial settings should anticipate:

- display name
- default alert behavior
- whether to alert Next Up
- whether to alert Currently Serving
- preferred advance-warning distance, initially 1 student
- visual alert enabled
- sound alert enabled
- vibration enabled where supported
- push notification enabled where supported
- future retention preferences

Not all settings must be implemented in the first milestone, but the architecture should allow them cleanly.

## 14. Real-time behavior

Queue changes should propagate without manual refresh to:

- podium Master View
- instructor mobile Master View
- student Client Views

Flask-SocketIO is the initial real-time mechanism.

The server/database remain authoritative.

## 15. QR code

Each active session shall provide a QR code containing the public Client View URL for that session.

The QR code should be prominent and easy to scan from a classroom display.

## 16. Accessibility and responsive design

The application should:

- work on current mobile and desktop browsers
- use large, clear touch targets
- not rely on color alone to convey state
- provide text equivalents for alerts/status
- use semantic HTML where practical
- keep the Client View lightweight

## 17. Deployment requirements

Production target:

- Azure App Service
- Azure Database for PostgreSQL Flexible Server

Source control:

- GitHub

CI/CD target:

- GitHub Actions

Initial Socket.IO deployment assumes a single application worker.

## 18. Explicit non-goals for initial implementation

Do not implement unless explicitly requested:

- student login/accounts
- student location collection
- seat/workstation tracking
- native iOS or Android apps
- Redis
- multi-worker Socket.IO scaling
- institutional SSO
- administrator portal
- cross-college analytics
- complex appointment scheduling
- chat/messaging between instructor and students
