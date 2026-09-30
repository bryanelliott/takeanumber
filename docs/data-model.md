# Take A Number — Initial Data Model

This document is a design target, not permission to implement every table immediately.

Use UUID primary keys unless there is a strong documented reason not to.

## 1. Instructor

Represents an authenticated faculty account.

Suggested fields:

```text
id                  UUID PK
email               VARCHAR / CITEXT-like semantics if practical
display_name        VARCHAR
password_hash       VARCHAR
is_active           BOOLEAN
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
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
created_at                  TIMESTAMPTZ
updated_at                  TIMESTAMPTZ
```

Initial default:

```text
advance_warning_count = 1
```

Settings can be introduced after core queue functionality if desired.

## 3. HelpSession

Represents one instructor's lab queue session.

Suggested fields:

```text
id                  UUID PK
instructor_id       UUID FK -> instructor.id
public_code         VARCHAR
status              VARCHAR or enum-like constrained value
started_at          TIMESTAMPTZ
ended_at            TIMESTAMPTZ nullable
next_queue_number   INTEGER
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

Constraints:

- public_code unique
- instructor_id required
- status required
- started_at required
- next_queue_number >= 1

Business rule:

- Prefer at most one active session per instructor.

Milestone 2 enforces this with the PostgreSQL partial unique index
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
first_seen_at       TIMESTAMPTZ
last_seen_at        TIMESTAMPTZ
created_at          TIMESTAMPTZ
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
display_name        VARCHAR nullable
status              VARCHAR or constrained value
joined_at           TIMESTAMPTZ
service_started_at  TIMESTAMPTZ nullable
completed_at        TIMESTAMPTZ nullable
left_at             TIMESTAMPTZ nullable
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
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

Because "active" spans selected statuses, PostgreSQL partial unique indexes may be appropriate:

```text
UNIQUE(session_id, student_identity_id)
WHERE status IN ('waiting', 'serving')
```

If Flask-Migrate autogeneration does not produce the desired partial index correctly, write the migration explicitly and test it.

Milestone 3 explicitly creates `uq_queue_entry_active_identity` on
`(session_id, student_identity_id)` for `waiting` and `serving` in migration
`0003_student_queue`. `uq_queue_entry_session_number` prevents reusing any number,
including historical entries. Foreign keys restrict deletion of referenced
sessions/identities. Names are optional, trimmed, limited to 100 characters, and
stored only on the request. Blank names become NULL.

Timestamp constraints enforce the shapes of waiting, serving, completed, and
left records. Milestone 3 implements only joining (waiting) and leaving (left).
Serving/completed fields preserve the schema needed by the next milestone, but
there are no advancement endpoints. A leave retains the request, its number,
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
created_at           TIMESTAMPTZ
updated_at           TIMESTAMPTZ
revoked_at           TIMESTAMPTZ nullable
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

Store UTC in PostgreSQL via `TIMESTAMPTZ`.

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
