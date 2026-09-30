# Take A Number — Initial UI States

This document defines behavior/state, not final visual design.

## Master View states

### Active, empty queue

Display:

- session active
- QR code
- no one currently serving
- no one next
- queue empty
- End Session enabled

### Active, waiting students, nobody serving yet

Display:

- no one currently serving
- first waiting student as Next Up or provide a Start/Serve action depending on final queue semantics

Milestone 3 choice: every join creates a `waiting` request, including the first
request. Becoming first in line does not automatically begin service. Instructor
advancement will explicitly begin service in Milestone 4; its controls are not
part of Milestone 3.

### Active, serving

Display:

- Currently Serving
- Next Up
- truncated queue
- waiting total
- Done
- End Session

### Ended

Display:

- session ended
- historical summary link
- no queue mutation controls

## Client View states

### Not joined

Display:

- session/instructor context
- optional name input
- Take A Number
- optional alert explanation

### Waiting

Display:

- queue number
- people ahead
- estimated wait
- Leave Queue
- Exit

Milestone 3 shows queue number, people ahead, and waiting state. Estimated wait
is explicitly unavailable until Milestone 6. Refresh status reloads server state;
there are no Socket.IO updates or automatic alerts yet. Only this browser's name
and request are visible, never another browser's request or entered name.

### Next Up

Display:

- strong "You're next" message
- visual alert state
- sound/vibration when enabled and supported
- queue number
- Leave Queue if product rules still allow it

### Currently Serving

Display:

- strong "It's your turn" message
- visual alert
- sound/vibration when enabled and supported

### Left Queue

Display:

- confirmation that the active request was removed
- option to take a new number if session is still active

### Session Ended

Display:

- session ended
- no Take A Number action
- no stale wait estimate

Milestone 3 preserves unfinished `waiting` records when the session ends. The
ended session makes those records inactive for participation, and the Client View
shows only the ended state with no join/leave controls. It does not claim that a
request was completed or voluntarily left.

### Exit passive view

Exit navigates to a read-only page with a Return to session link. It does not
change queue entries, identity timestamps, or the browser cookie. Returning with
the cookie intact restores the current request. Leave Queue is a separate POST
that records `left_at` and retains the historical request. Rejoining gets a new
number; repeating an old Leave cannot remove the new request.

## Accessibility notes

- Do not convey Next Up/Serving solely through color.
- Use text and iconography.
- Avoid rapid flashing patterns that create accessibility risk.
- Respect reduced-motion preferences where feasible.
- Audio must not be the sole alert mechanism.
