# Take A Number — Initial Data Model

This document is a design target, not permission to implement every table immediately.

Use UUID primary keys unless there is a strong documented reason not to.
SQLAlchemy `Uuid` maps to SQL Server UNIQUEIDENTIFIER; UUIDs are generated in Python.
`0001_sqlserver_baseline` contains the five currently implemented tables. Future
push/metrics tables remain deferred. Booleans map to BIT. Display names use NVARCHAR
with an explicit 100-code-point check so supplementary Unicode characters round-trip.
Public codes, token hashes, password hashes and status values use binary collations
to preserve case-sensitive comparisons. Nullable token hashes use a filtered unique
index (`IS NOT NULL`) so multiple retained identities can be unlinked independently.

## 1. Instructor

Represents an authenticated faculty account.

Suggested fields:

```text
id                  UUID PK
email               VARCHAR(254), normalized lowercase ASCII/IDNA
display_name        NVARCHAR(200), max 100 Unicode characters
password_hash       VARCHAR
is_active           BOOLEAN
created_at          DATETIMEOFFSET
updated_at          DATETIMEOFFSET
```

Constraints:

- email unique
- email required
- password_hash required
- display_name required

Indexes:

- unique email

## 2. InstructorSetting

One-to-one settings record.

Suggested fields:

```text
id                          UUID PK
instructor_id               UUID FK -> instructor.id, unique
alert_next_enabled          BOOLEAN
alert_serving_enabled       BOOLEAN
visual_alert_enabled        BOOLEAN
sound_alert_enabled         BOOLEAN
vibration_enabled           BOOLEAN
push_enabled                BOOLEAN
advance_warning_count       INTEGER
created_at                  DATETIMEOFFSET
updated_at                  DATETIMEOFFSET
```

Initial default:

```text
advance_warning_count = 1
```

Milestone 8 implements the fields above except `push_enabled`, which is deferred
until Web Push exists. All five implemented booleans default to true. Sound and
vibration settings permit student opt-in; they never automatically enable media.
The warning count is non-null and constrained to integers 1–3 in SQL Server and
the settings form. The instructor foreign key is non-null and unique; deletion
of an instructor cascades to its preferences (no instructor deletion UI is added).

The initial SQL Server baseline includes this table. Registration inserts
its settings in the same transaction. Reads do
not create records; accounts provisioned outside registration use safe defaults
until saved. Saves use a `UPDLOCK, HOLDLOCK` select followed by insert/update in one transaction,
so concurrent saves cannot create duplicates. The last committed complete form
wins. Baseline downgrade drops all implemented application tables and is tested
only on the disposable test database.

## 3. HelpSession

Represents one instructor's lab queue session.

Suggested fields:

```text
id                  UUID PK
instructor_id       UUID FK -> instructor.id
public_code         VARCHAR
status              VARCHAR or enum-like constrained value
started_at          DATETIMEOFFSET
ended_at            DATETIMEOFFSET nullable
next_queue_number   INTEGER
created_at          DATETIMEOFFSET
updated_at          DATETIMEOFFSET
```

Constraints:

- public_code unique
- instructor_id required
- status required
- started_at required
- next_queue_number >= 1

Business rule:

- Prefer at most one active session per instructor.

Milestone 2 enforces this with the SQL Server filtered unique index
`uq_help_session_active_instructor` on `instructor_id` where `status = 'active'`.
The start-session service also locks the instructor row: concurrent or repeated
starts return the same active session. Starting after it ends creates a new record.

Implemented lifecycle details:

- UUID primary key and a separate 22-character URL-safe public code generated from
  128 random bits; codes are unique across active and ended sessions.
- The instructor foreign key restricts deletion, preserving session history.
- Status is restricted to `active` or `ended`. Active sessions have no `ended_at`;
  ended sessions require `ended_at >= started_at`.
- End locks the session row and changes the state only once. Retrying preserves
  the original end timestamp. Ownership is checked before reading or ending it.
- `next_queue_number` starts at 1 and is advanced only for a new queue entry in the
  same transaction as its insertion, while holding the session row lock.
- `session_for_join(public_code)` locks and checks current state without committing.
  The queue service inserts or leaves its entry in that same transaction and
  commits or rolls back. Missing/ended sessions are rejected.

## 4. StudentIdentity

Represents a pseudonymous browser/device profile, not a verified person.

Suggested fields:

```text
id                  UUID PK
public_token_hash   VARCHAR or BYTEA
first_seen_at       DATETIMEOFFSET
last_seen_at        DATETIMEOFFSET
created_at          DATETIMEOFFSET
```

Important:

- Do not store an unnecessary raw secret token if a hash will serve the lookup design.
- Do not fingerprint the browser.
- Do not attach location data.
- A browser identity is not proof of a human identity.

Milestone 3 stores a unique SHA-256 hash of a random 256-bit browser token. The raw
token exists only in the signed HttpOnly browser cookie, never in the database or
URLs. `first_seen_at`/`created_at` record the first successful join; `last_seen_at`
updates on successful join attempts and actual leaves, not passive page reads.
The token hash is nullable so an approved future retention policy can unlink the
browser while preserving referenced history. No automatic retention runs yet.

## 5. QueueEntry

Represents one request for help in one session.

Suggested fields:

```text
id                  UUID PK
session_id          UUID FK -> help_session.id
student_identity_id UUID FK -> student_identity.id
queue_number        INTEGER
display_name        NVARCHAR(200), max 100 Unicode characters nullable
status              VARCHAR or constrained value
joined_at           DATETIMEOFFSET
service_started_at  DATETIMEOFFSET nullable
completed_at        DATETIMEOFFSET nullable
left_at             DATETIMEOFFSET nullable
created_at          DATETIMEOFFSET
updated_at          DATETIMEOFFSET
```

Recommended statuses:

```text
waiting
serving
completed
left
```

Potential future status:

```text
cancelled
```

Constraints:

- session_id required
- student_identity_id required
- queue_number required
- joined_at required
- unique `(session_id, queue_number)`

Critical invariant:

A student identity may have at most one active queue entry per session.

Because "active" spans selected statuses, SQL Server filtered unique indexes may be appropriate:

```text
UNIQUE(session_id, student_identity_id)
WHERE status IN ('waiting', 'serving')
```

If Flask-Migrate autogeneration does not produce the desired filtered index correctly, write the migration explicitly and test it.

Milestone 3 explicitly creates `uq_queue_entry_active_identity` on
`(session_id, student_identity_id)` for `waiting` and `serving` in migration
`0001_sqlserver_baseline`. `uq_queue_entry_session_number` prevents reusing any number,
including historical entries. Foreign keys restrict deletion of referenced
sessions/identities. Names are optional, trimmed, limited to 100 characters, and
stored only on the request. Blank names become NULL.

Timestamp constraints enforce the shapes of waiting, serving, completed, and
left records. Milestone 4 adds the explicit filtered unique index
`uq_queue_entry_serving_session` on `session_id` where `status = 'serving'`, in
migration `0001_sqlserver_baseline`. This permits at most one serving entry per
session; it does not alter session-scoped queue numbers or existing history.
All indexes are created with the initial tables. Future changes must preserve
these constraints; no migration silently rewrites queue history.

Serve next changes the first waiting entry to serving and records its start.
Done changes the displayed serving entry to completed with `completed_at` and
promotes the next waiting entry, sharing the same transition timestamp. Repeated
or stale submissions cannot overwrite timestamps or complete the successor.
A leave retains the request, its number,
join timestamp, optional name, and any existing service-start timestamp. Ended
sessions retain unfinished entries without fabricating service or leave times.

## 6. PushSubscription

Future table for web push.

Suggested fields:

```text
id                  UUID PK
student_identity_id UUID FK -> student_identity.id
endpoint_hash       VARCHAR
endpoint            TEXT
p256dh               TEXT
auth                 TEXT
created_at           DATETIMEOFFSET
updated_at           DATETIMEOFFSET
revoked_at           DATETIMEOFFSET nullable
```

Treat subscription fields as sensitive application data.

Do not implement until push notification work begins.

## 7. Relationships

```text
Instructor
  1
  |
  +----< HelpSession
  |
  +----1 InstructorSetting

StudentIdentity
  1
  |
  +----< QueueEntry >----1 HelpSession
```

## 8. Time handling

Use timezone-aware timestamps.

Store timezone-aware instants through SQLAlchemy `DateTime(timezone=True)`,
mapped to SQL Server `DATETIMEOFFSET`. Azure SQL uses UTC; Python timestamps use
UTC and SQL transition/default timestamps use `SYSDATETIMEOFFSET()`. Duration
queries use `DATEDIFF_BIG(microsecond, ...)` with decimal arithmetic.

Convert to local display time only in the presentation layer.

## 9. Derived metrics

Do not initially store:

- help duration
- wait duration
- average help time
- average wait time

Derive:

```text
help_duration = completed_at - service_started_at
wait_duration = service_started_at - joined_at
```

Only completed/valid records should participate in relevant calculations.

## 10. Help-frequency metrics

Frequency by browser identity:

```text
COUNT(queue_entry.id)
GROUP BY student_identity_id
```

Frequency by entered name must be interpreted cautiously because:

- names may be blank
- names may differ in spelling/case
- multiple students may share a name
- a student may use multiple devices

Do not merge identities automatically based solely on name.

## 11. Queue ordering

Queue order should be determined by queue sequence/number and active status, not by mutable client state.

The session's next queue number should be allocated atomically to avoid duplicates.

## 12. Deletion and retention

Do not implement destructive retention behavior until retention requirements are explicitly approved.

However, the schema should not prevent future cleanup of:

- student-entered names
- pseudonymous identity records
- push subscriptions

Historical aggregate reporting requirements should be considered before deletion policies are added.
