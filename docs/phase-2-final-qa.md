# Phase 2 final QA — Milestone 2.6

## Audit scope and initial findings

Audit started from a clean working tree after deployed Milestone 2.5. The actual
database is SQL Server/Azure SQL, not PostgreSQL. No production database is used.
Source review covers public/auth/instructor/queue blueprints, service-owned queue
transitions, signed browser identity, CSRF/ownership, shared templates and tokens,
live updates, existing tests, startup and Azure CI/deployment assumptions.

The initial findings were recorded before corrective application changes. The
enlarged-text defect was then reproduced in Chrome. Final dispositions follow.

| ID | Component | Severity | Finding / evidence | Recommended correction | Disposition |
| --- | --- | --- | --- | --- | --- |
| QA-001 | Master / Client connection status | High | Status appeared below the fold while old tickets remained prominent: at 1920×1080 Master Serving status began at y=1248; at 320×568 Client Waiting status began at y=1320. | Place one persistent status region before queue data, label potentially stale state explicitly, verify projection still fits. | Fixed |
| QA-002 | Network recovery | Medium | Shared updater handled socket reconnect/visibility/polling but did not listen for browser online/offline events. Socket-unavailable recovery waited for the next poll. | Reuse the serialized refresh on online; report offline immediately, without adding a timer or changing the protocol. | Fixed |
| QA-003 | No-JavaScript fallback | Medium | Shared status said “Connecting live updates” even without JavaScript. | Hide the connecting status until JS initializes; retain an explicit noscript instruction. | Fixed |
| QA-004 | Repeatable rendering QA | Medium | Previous full-template viewport scripts and screenshots lived in ignored local preview files, so ordinary checkout could not rerun that coverage. | Add optional browser-marked tests using existing Chrome/CDP and Python dependencies, with locally exportable screenshots/results. | Fixed |
| QA-005 | Physical devices / assistive technology | Medium | Desktop automation cannot establish mobile keyboard, iOS media, physical QR distance or screen-reader behavior. | Document a release checklist with specific scenarios and owners to verify on staging. | Requires Manual Verification |
| QA-006 | Generic HTTP/database error presentation | Low | Default HTTP error pages and the generic JSON database-unavailable response are plain but do not expose exception details. | Preserve existing response/status contracts; consider a separate future error-shell task. | Deferred |
| QA-007 | Enlarged text / reflow | Medium | At 320px and 200% root text size: landing headline, Master Serve next/Done minimum widths, and Client advance-warning heading caused horizontal overflow. | Allow the headline/alert heading to wrap and constrain action minimum widths to available space. | Fixed |

## Views and states to verify

- Public landing, anonymous and authenticated navigation.
- Login, signup, rate-limited attempts, validation and flash messages.
- Dashboard without/with an active session; instructor settings.
- Master empty, waiting, serving and ended; standard and Presentation Mode.
- Client not joined, waiting, Next Up, advance warning, serving, completed, left,
  ended, Exit, unknown session and changed/missing browser identity.
- Temporary connection failures, offline/online, retry, foreground reconciliation,
  authorization loss, stale responses and unsupported optional alert APIs.
- Default HTTP errors and generic database-unavailable response via regression tests.

## Executive summary

Milestone 2.6 makes targeted CSS/template and shared-updater corrections, without
changing routes, queue services, SQL Server models, authentication, CSRF or browser
identity. Seven findings: **0 Critical, 1 High, 5 Medium, 1 Low**. Five are fixed;
one Medium requires physical-device/assistive-technology verification and one Low
cosmetic issue is deferred. No known Critical or High defect remains within the
audited scope. Final acceptance is recommended after the manual staging checklist.

## Responsive and browser evidence

Installed host Chrome rendered the real Flask/Jinja templates over loopback HTTP.
Service snapshots and the socket transport were synthetic; HTTP state reads, local
assets, QR generation and browser DOM/CSS/JavaScript were real. This is not a
browser-to-SQL end-to-end or production-load test. SQL-backed regression tests are
separate. No production data or credentials were used.

Each matrix row covers 24 presentations: both landing authentication states,
login/signup, both dashboard states, settings, three active Master states in both
modes, ended Master, eight Client states, Exit and unknown session.

| Viewport | Actual Chrome renders | Overflow / semantics / sampled contrast / images |
| --- | ---: | --- |
| 320×568 | 24 | Pass |
| 375×667 | 24 | Pass |
| 390×844 | 24 | Pass |
| 430×932 | 24 | Pass |
| 768×1024 | 24 | Pass |
| 1024×768 | 24 | Pass |
| 1280×800 | 24 | Pass |
| 1440×900 | 24 | Pass |
| 1920×1080 | 24 | Pass |
| 2560×1440 | 24 | Pass |

All active Master QR images remained square and on the right at desktop widths.
At 1920×1080 and 2560×1440, Currently Serving, Next Up and QR were above the fold.
At 1920×1080 the QR measured 712px in standard mode and 840px in Presentation Mode.
The new connection region remains visible at all standard tested sizes; warning
states also fit above the fold on 390×844 Client and 1920×1080 Master in both modes.
Longer content and zoom may require vertical scrolling; no fixed-height clipping
was introduced. The unchanged generator provides the four-module white quiet zone
and the actual `url_for()` student URL; regression tests verify destination/ownership.

Twenty non-presentation page states also passed 320px reflow with enlarged 200%
root text, and separately with line height 1.5, letter spacing .12em, word spacing
.16em and paragraph spacing 2em. These are text/reflow checks, **not native browser
zoom testing**. Presentation exit, focus return, QR DOM persistence, network
offline/online reconciliation and JavaScript-disabled fallback were exercised.

Screenshots actually created: 72 page screenshots (all 24 at 320, 390 and 1920px)
and three offline-state screenshots, under ignored `instance/final-qa/final/`.
Per-viewport JSON and reflow JSON accompany them. These artifacts are local and
not committed. Master desktop and Client phone screenshots were visually inspected.

## Accessibility and visual consistency

Automated DOM checks cover one main landmark/H1, document language, unique IDs,
accessible control names, ARIA reference targets, image alternatives/loading,
visible button height of at least 44px, and text contrast for visible direct text
against opaque ancestor backgrounds. Sampled text contrast was at least 5.45:1.
This limited checker does not cover every pseudo-element, native control, gradient,
focus state or assistive technology. It is not a WCAG certification.

Real keyboard events verified the login skip link, main focus, email tab order and
visible focus outline; Presentation Mode Escape returns focus to its toggle.
Existing browser cases verify password toggles, submit recovery, Client focus,
drafts/validation retention, disclosure state and deduplicated live announcements.
Source review confirmed associated form labels/errors, semantic headings, native
controls, shared focus styles and reduced-motion rules. No new animation exists.

Methodology references: W3C [reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[text spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html), and
[focus not obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).
Manual checks below remain necessary for screen readers, native zoom and non-text
contrast across devices. Shared connection styling replaces duplicated Master/Client
rules; existing typography, colors, buttons and form components remain the foundation.

## Performance and connection reliability

The landing page uses local responsive WebP: 143,824-byte small image and
407,228-byte main image, with declared aspect ratio. Chrome at 390px requested the
small image. The unused source PNG is not downloaded. The landing has no required
JavaScript; queue pages retain the existing 46,831-byte local Socket.IO library and
focused scripts. No font CDN, new runtime dependency or redundant polling loop was
added. QR remains outside the changing fragment and is not regenerated on updates.

The harness records navigation/resource timings and sampled layout shifts, but
uses a warm local browser, synthetic socket callbacks and programmatic mode toggles.
Cached resources can report zero transferred bytes; mode changes/enhancement affect
layout-shift observations. These measurements are diagnostic artifacts, **not field
Core Web Vitals or Lighthouse scores**. No production performance claim is made.
Cold-load/throttled-device performance remains a staging measurement; no speculative
asset rewrite was justified.

Offline is reported immediately; successful online reconciliation clears the warning.
Failed reads preserve the last known state and explicitly warn it may be stale.
Reads remain serialized, with the existing timeout, Socket.IO invalidation and
30-second fallback poll. Online/visibility events reuse that same reader. Authorization
loss still clears private state and stops updates; online/offline cannot restart it.
No-JavaScript pages retain ordinary CSRF-protected forms and manual-refresh guidance.

## Regression results and security review

- `docker compose run --rm test-runner python scripts/init_test_database.py`: passed,
  dedicated disposable SQL Server test database only.
- `docker compose run --rm test-runner python -m pytest`: **374 passed, 23 skipped**
  (browser tooling unavailable in the container).
- Host `python -m pytest tests/test_live_browser.py tests/test_ui_browser.py -q`:
  **23 passed** in installed Chrome, including all cases skipped in the container.
- `python -m ruff check .`: passed. `git diff --check`: passed.

Existing coverage was retained for signup/password/validation, generic login errors,
logout, rate limits, safe redirects, session expiry, CSRF, instructor isolation,
settings persistence, queue creation/duplicate joining/order/position/advancement,
completion/leaving/ending, identity persistence, HTTPS referrer handling, live
authorization/invalidation, QR destination and production configuration/migrations/
startup. Default error paths preserve safe status/response contracts. New browser
coverage exercises failure/recovery, layout and accessibility across the whole UI.

No backend Python, authorization, student identity, model, migration, security
configuration or deployment file changed. Names continue through Jinja escaping;
no new identifier exposure, storage, analytics, geolocation or external resources
were introduced. The original missing-referrer issue already has the same-origin
response policy and positive/negative HTTPS regression tests; CSRF was not relaxed.

## Manual verification and outstanding items

The release owner should record staging results before final acceptance:

1. On iOS Safari, Android Chrome and desktop browsers, repeat login/signup/settings
   and anonymous QR join at 320–430px, tablet portrait/landscape and desktop sizes.
   Check software keyboard, autofill, pinch zoom, safe areas and native zoom at 200%.
2. With NVDA/VoiceOver and keyboard only, follow labels/help/errors, password toggles,
   queue changes, Leave disclosure and presentation entry/exit. Confirm unchanged
   polls remain quiet and warning announcements are understandable. Check focus
   and non-text contrast, high contrast/forced colors and reduced motion.
3. Project at 1920×1080 and 2560×1440. Check reading distance and scan the real HTTPS
   QR with multiple physical phones. The local screenshots cannot prove distance,
   glare, camera behavior or production network reachability.
4. Use two instructors, two student browsers and two Master tabs: start, join twice,
   refresh, leave, Serve next, Done and End. Verify ownership, numbers, counts,
   Next Up versus Serving, settings policy and synchronized updates. Exit must not
   leave the queue. Clear a student's cookies and confirm explicit recovery guidance.
5. Disconnect/reconnect actual Wi-Fi; background/resume a phone. Verify stale warning,
   recovery, unchanged QR and fresh status. Log out in another tab and verify private
   state clears. Test optional sound/vibration permitted, denied and unsupported.
6. Disable JavaScript and use forms/manual Refresh. On staging, verify invalid forms,
   throttled login, expired CSRF and unknown session responses expose no internals.
   Measure cold-load performance on a throttled real device if release targets require it.

QA-005 remains manual; QA-006 is a deferred cosmetic follow-up. Existing browser
identity cannot recover a ticket after cookie loss across browsers. Background or
sleeping devices may delay updates and optional alerts. These are documented existing
limits, not new promises or identity/notification infrastructure changes.

## Reproducing the optional browser audit

Use the existing virtual environment and locally installed Chrome/Chromium/Edge:

```powershell
$env:UI_QA_ARTIFACT_DIR = Join-Path (Get-Location) 'instance/final-qa/final'
python -m pytest tests/test_live_browser.py tests/test_ui_browser.py -q
```

Without a supported browser these tests explicitly skip. They use existing
`simple-websocket`/CDP, no new package or browser download. Synthetic preview state
never opens the configured fake SQL connection. Browser tests retain the existing
`browser` marker and remain outside the production CI deployment gate.

## Deployment and final acceptance checklist

Changed-file inventory:

- Added `app/templates/_live_status.html` — shared persistent feedback/fallback.
- Modified `app/templates/_live_updates.html`, `app/templates/instructor/master.html`
  and `app/templates/queue/client.html` — compose the status before queue data.
- Modified `app/static/live-updates.js` — explicit stale/offline/recovery feedback.
- Modified `app/static/css/design-system.css`, `app/static/css/master.css`,
  `app/static/css/client.css` and `app/static/css/landing.css` — shared feedback,
  QR height allowance and narrow enlarged-text corrections.
- Modified `tests/browser_live_updates.html`; added `tests/test_ui_browser.py` and
  `tests/ui_audit.js` — reliability and repeatable full-template browser checks.
- Added this report; updated `docs/phase-2-ui.md` — conventions and release guidance.

Deploy changed templates, CSS and JavaScript together through the existing Azure
workflow. No new dependencies, environment settings, infrastructure or database
migrations are required. Existing migration-before-Gunicorn startup and one-worker
Socket.IO assumptions remain unchanged. No deployment was performed by this task.

- [x] All implemented public/instructor/student views inventoried and audited.
- [x] No known Critical/High defect remains in the audited Phase 2 scope.
- [x] Targeted fixes preserve queue/security/database contracts.
- [x] All ten viewport sizes rendered; screenshots and focused accessibility checks run.
- [x] SQL Server regression suite and Ruff pass.
- [x] Manual limitations and deferred error-page polish recorded.
- [ ] Release owner completes physical devices, native zoom, screen readers and projector checks.
- [ ] Staging smoke test confirms deployed assets, HTTPS QR entry and multi-browser updates.
