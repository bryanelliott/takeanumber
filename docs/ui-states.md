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
- no Serve next or Done control
- End Session enabled

### Active, waiting students, nobody serving yet

Display:

- no one currently serving
- first waiting request as Next Up
- Serve next starts that request; Done is hidden until somebody is serving

Every join creates a `waiting` request, including the first request. Becoming
first in line does not automatically begin service. Milestone 4 uses a single
**Serve next** action when nobody is serving. It starts the first waiting request
and records `service_started_at`. It does not complete anything. If that request
left after the page loaded, the action changes nothing and refreshes the view.
The same behavior applies if the currently served request leaves voluntarily:
the instructor explicitly selects Serve next again.

### Active, serving

Display:

- Currently Serving
- Next Up
- truncated queue
- waiting total
- Done
- End Session

Done completes the request displayed as Currently Serving and starts the first
waiting request in the same transaction. With no waiting requests, it leaves
nobody serving. Done submitted with nobody serving changes nothing; it never
acts as Serve next. Repeated or stale controls cannot complete a different
request. Each action targets the entry shown when the form was rendered.

Total waiting excludes Currently Serving, completed, and left requests. Next Up
is the lowest waiting queue number. The truncated list shows the first five
waiting requests, including Next Up, and states how many are shown out of the
total. Optional entered names accompany queue numbers and are HTML-escaped.
Names on the Master View may be visible on the instructor's classroom display.

Milestone 4 reads a consistent database snapshot on each load and after each
action. Refresh queue loads changes from other browsers. Automatic synchronization
is deferred to Milestone 5. The active view includes a prominent QR code and the
equivalent public Client View link; neither contains an instructor credential.

### Ended

Display:

- session ended
- historical summary link
- no queue mutation controls

Historical summaries remain deferred to Milestone 9; the current ended view
shows the end time and a dashboard link. It hides the QR and live queue panels.

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

Unfinished `waiting` and `serving` records are preserved when the session ends. The
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
