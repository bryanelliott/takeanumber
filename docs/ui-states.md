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

Before implementation, Codex must resolve this with the current product behavior:
- either joining the first student automatically makes them serving, or
- the instructor explicitly begins service

Do not silently choose without documenting the chosen behavior.

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

## Accessibility notes

- Do not convey Next Up/Serving solely through color.
- Use text and iconography.
- Avoid rapid flashing patterns that create accessibility risk.
- Respect reduced-motion preferences where feasible.
- Audio must not be the sole alert mechanism.
