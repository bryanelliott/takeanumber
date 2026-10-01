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

Milestone 5 reads a consistent database snapshot on each load, after each action,
and automatically when notified of committed changes in another browser. Refresh
queue remains available. The active view includes a prominent QR code and the
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

The Client View shows queue number, people ahead, current state, and an approximate
wait while waiting. Milestone 6 uses at least 3 current-session completions or the
instructor's valid completed helps from other ended sessions in the last 90 days.
The full policy is documented under WaitTimeService in `architecture.md`.
The final estimate is rounded up to whole minutes and shown as `About N minutes`.
With people ahead and insufficient history, display `Not enough completed help
history yet`. With nobody ahead, display `No one ahead; waiting for the instructor`.
The serving request ahead counts as one expected help; elapsed time is not
subtracted. Estimates do not include instructor pauses and are not a countdown.
Hide estimates outside the waiting state. Live updates recalculate the estimate;
Refresh status remains available. Phase 7A adds optional sound/vibration; Web Push remains deferred. Only this browser's name
and request are visible, never another browser's request or entered name.

### Next Up

Display:

- strong "You're next" message
- visual alert state
- sound/vibration when enabled and supported
- queue number
- Leave Queue if product rules still allow it

Phase 7A defines Next Up as the **first waiting request**, matching the Master
View. This applies whether someone is serving or the instructor has not begun
service yet. One person ahead alone does not determine Next Up: that person might
still be waiting. Next Up remains a waiting request, with its usual estimate and
Leave Queue action. Display a prominent `You're next` heading, arrow, dashed
border, queue number, and reminder to wait for the instructor to begin service.

### Currently Serving

Display:

- strong "It's your turn" message
- visual alert
- sound/vibration when enabled and supported

The serving view prominently shows `It's your turn`, a check icon, solid border,
and `Currently serving: number N`. Leave Queue remains available under the existing
rules. Neither alert animates or flashes; both remain static with reduced motion.

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

## Connection state (Milestone 5)

Master and Client Views show live connection status. They fetch current state on
connection/reconnection, when a tab becomes visible, and every 30 seconds as a
fallback. Notices contain no queue details; each view fetches only authorized
server-rendered state. Updates preserve an optional name being typed. Lost access
or a missing/expired browser cookie clears the stale view and asks for a reload.
Session End automatically shows the ended state and removes queue controls.
Closing the page or losing a connection never invokes Leave Queue. With JavaScript
disabled, all ordinary forms and manual refresh continue to work.

## Accessibility notes

- Do not convey Next Up/Serving solely through color.
- Use text and iconography.
- Avoid rapid flashing patterns that create accessibility risk.
- Respect reduced-motion preferences where feasible.
- Audio must not be the sole alert mechanism.

## Optional in-browser alerts (Phase 7A)

Visual states render on the server and work without JavaScript or media APIs.
While participating, the page offers separate **Enable and test sound** and
**Enable and test vibration** buttons, subject to the instructor's settings.
Both are off initially. Sound initializes
or resumes its audio context only through the student's button click. Buttons
also allow turning effects off. Missing or denied capabilities show explanatory
text and leave all queue controls functional. A short test does not replay a
previous queue transition.

After a committed queue change, the existing live refresh reads authoritative
private state. New Next Up/Serving states trigger enabled effects at most once per
request and alert kind in that page. Repeated refreshes or reconnects do not repeat
them. Initial page load establishes the baseline without automatic sound/vibration.
If disconnected across several transitions, only the current state is presented;
old alerts are not replayed. A new request can alert again.

A stable polite screen-reader region announces changed alert text, and the tab
title reflects the current alert. Focus is not moved by alerts. On leave,
completion, session end, loss of view access, or page exit, effects turn off and
stale alert text/title are cleared. Preferences are in-page only: reload/return
requires enabling effects again. No settings, permissions, or identifiers are
stored for these student choices. Keep the page open; background/sleeping browsers or
device settings can suppress sound/vibration. Web Push and service workers are
not implemented in Phase 7A.

## Instructor settings (Milestone 8)

Instructor navigation links to **Settings**. The authenticated instructor can
change Next Up/advance-warning alerts, Currently Serving alerts, visual emphasis,
optional sound, optional vibration, and warning distance. Defaults enable the
events and visual emphasis and allow student media opt-in. Web Push is explicitly
unavailable; there is no inactive push checkbox or location setting.

Warning distance accepts 1, 2, or 3 waiting requests (default 1), excluding serving,
left, and completed requests. Only the first waiting request says **You're next**;
other requests inside the distance say **Your turn is approaching**. With no one
serving, the same rule applies. The instructor must still select Serve next.
The Next Up toggle controls both warning kinds. Each can signal once when newly
observed, followed by a separate Serving signal when applicable.

Disabling an event or visual emphasis removes its alert styling; plain Next Up
and Currently Serving text, position, estimates, and queue controls remain. Visual
emphasis controls tab titles and polite alert announcements too. Media toggles
disable student enable/test buttons with an explanation; enabling a toggle never
enables media automatically. Active pages refresh after a settings save, without
sounding for the settings edit itself or replaying an old alert. Changes apply to
current and future sessions. Validation failures display errors without saving.
