# Phase 2 UI foundation — Milestones 2.1 and 2.2

## Scope and direction

The public `public` blueprint serves `/` without authentication. It uses the
existing `auth.signup`, `auth.login`, and `instructor.dashboard` endpoints. Signed-in
instructors can still view the landing page and open their dashboard. Authentication
redirects, logout POST/CSRF, instructor authorization, queue services, and student
access are unchanged. `/health` remains a separate database-independent endpoint.

The visual direction is calm and approachable: forest green actions, blue links,
neutral surfaces, legible system typography, subtle borders and shadows. Text sits
above the landscape, with the entire image visible at every size. The shared shell
lightly improves instructor and authentication pages. The Master View retains its
two-column queue/QR layout in these initial milestones; Milestone 2.3 below replaces
that layout. Its CSS lives in `master.css`. Milestone 2.4 below brings the independent
student shell and queue layouts onto the same design foundation.
Milestone 2.5 below completes the authentication, settings and dashboard treatment.

## Files and components

- `app/public/`: small blueprint for the public landing route.
- `app/templates/base.html`: shared document, stylesheet, skip link, main region,
  categorized flash messages, header and footer.
- `app/templates/ui/_header.html`: brand/home link, responsive navigation, and
  authenticated dashboard/settings/CSRF-protected logout controls.
- `app/templates/ui/_footer.html`: application name and classroom description.
- `app/templates/ui/_flashes.html`: consumes categorized Flask flashes once.
- `app/templates/ui/components.html`: `button_link`, `icon`, `alert`, and `field`
  macros. Text remains escaped. Icons are decorative inline SVG, requiring no library.
- `app/templates/auth/_fields.html`: compatibility wrapper for the shared field
  macro, preserving existing authentication-template imports.
- `app/templates/public/landing.html`: hero, supported feature descriptions,
  authentication links, and guidance for students who have a session link/QR code.
- `app/static/css/design-system.css`: tokens, base typography and shared components.
- `app/static/css/landing.css`: landing layout only.
- `app/static/css/master.css`: existing Master-specific layout, scoped to avoid
  overriding the new shared header.
- `app/static/images/`: source artwork and optimized local delivery copies.

No frontend framework, bundler, icon package, remote font, JavaScript, runtime
dependency, environment variable, or database migration was added. The database
remains SQL Server/Azure SQL. Azure startup and deployment configuration are unchanged.

## Tokens and layout primitives

Tokens live in `:root` in `design-system.css`. Prefer semantic tokens over copying
literal values into future page CSS:

| Tokens | Use |
| --- | --- |
| `--color-brand`, `--color-primary`, `--color-primary-hover`, `--color-secondary` | Brand, main actions and links |
| `--color-text`, `--color-text-muted` | Primary and secondary readable text |
| `--color-background`, `--color-surface`, `--color-surface-muted` | Page, panel and quiet surfaces |
| `--color-border`, `--color-control-border` | Dividers and higher-contrast form boundaries |
| `--color-success/warning/danger/info` and corresponding `-surface` tokens | Semantic status foreground/background pairs |
| `--font-family`, `--font-size-*`, `--font-weight-*`, `--line-height` | Local system fonts, fluid headings and body typography |
| `--space-1` through `--space-9` | Spacing from 0.25rem to 6rem |
| `--radius-sm/md/lg/pill`, `--shadow-sm/md` | Corners and restrained elevation |
| `--width-content/form/reading`, `--page-gutter` | 80rem shell, 36rem forms, 65ch copy and fluid gutters |
| `--focus-color`, `--focus-ring` | Visible, offset keyboard outline |

Compose `.container`, `.container--form`, `.page-content`, `.section-space`,
`.stack`, `.cluster`, `.grid`, `.reading-width`, and `.text-muted`. `.cluster`
wraps; `.grid` leaves column definitions to the page. Use `.panel` for a bordered
surface and `.card` for a surface with a subtle shadow. Avoid global page-specific
`body`/`nav` overrides. Base element rules use low specificity where practical.

## Template usage

```jinja
{% extends 'base.html' %}
{% from 'ui/components.html' import button_link, alert, field %}
{% block title %}Page title — Take A Number{% endblock %}
{% block content %}
  <h1>Page title</h1>
  {{ button_link('Open dashboard', url_for('instructor.dashboard')) }}
  {{ alert('Preferences saved.', 'success') }}
{% endblock %}
```

`button_link(label, href, variant='primary', arrow=false)` supports `primary`,
`secondary`, and `danger`. Links navigate; actual `<button type="submit">` controls
mutate state, inside POST forms with CSRF tokens. Use `.button--secondary` or
`.button--danger` on a button when appropriate. Plain buttons and submit inputs
inherit primary styling. Never replace a mutation form with a link for appearance.

`field(input, autocomplete)` renders the WTForms label, control, described error
region and `aria-invalid`. Forms must still call `form.hidden_tag()`. Use real
autocomplete values such as `username`, `current-password`, and `new-password`.

`alert(message, kind='info')` supports success, warning, danger and information,
each with a visible text label. Danger uses `role="alert"`; other kinds use
`role="status"`. Flashes map `error` to danger and uncategorized/unknown categories
to information. The macros never mark user-supplied messages as safe HTML.

Base blocks available to future pages: `title`, `head`, `body_class`, `main_class`,
`header`, `content`, and `footer`. Page styles belong in `head`; the shared CSS is
already loaded before that block. Authentication forms use
`container container--form page-content` for `main_class`.

## Artwork and performance

The provided artwork was found at `app/static/images/Landing-Hero.png`, rather
than the initially requested WebP path. The original remains intact. Delivery uses
`landing-hero.webp` (1672 × 941, 407,228 bytes) and `landing-hero-small.webp`
(836 × 471, 143,824 bytes), encoded from that artwork with Chrome's built-in WebP
encoder at quality 0.92. No image content was replaced or cropped. The original
PNG is 2,655,818 bytes; the full-size WebP is approximately 85% smaller.

The image uses `srcset`/`sizes` to let the browser select by rendered width and
pixel density, explicit dimensions/aspect ratio to reserve space, and high fetch
priority. It is above-the-fold content, so it is not lazy-loaded. Text is separate
from the image. CSS preserves the entire composition with automatic height.
Future replacements should preserve this aspect ratio or update the intrinsic
dimensions and aspect ratio together. Re-export delivery copies from the source
artwork using a WebP encoder at high quality; no runtime conversion is required.
Keep filenames/case consistent for Linux hosting and include both WebP files in
the deployment commit. Do not replace missing artwork with a remote stock image.

## Responsive and accessibility conventions

The default layout is one column. At 48rem, the landing introduction becomes two
columns and features become three columns. Gutters grow from 1rem to 3rem; content
is capped at 80rem on large screens. Navigation wraps into additional rows on small
screens rather than hiding controls behind a script. Artwork always scales intact.
Future Master/Client page layouts can choose their own breakpoints while reusing
tokens, surfaces, controls and focus styles.

Use one page H1, ordered headings, named navigation/sections, a main landmark and
descriptive image alt text. The visible-on-focus skip link targets focusable main
content. Shared buttons/navigation links have at least 44px height. Text and status
colors are paired with contrasting surfaces; status meaning also has text. Retain
labels, described validation errors, keyboard focus, and CSRF fields. Reduced-motion
preferences disable motion in the shared stylesheet; no landing animation is used.
These checks support WCAG AA-oriented development, not a complete accessibility audit.

## Verification and manual review

`tests/test_landing.py` covers anonymous access without a database query, links,
landmarks, local image/CSS delivery, authenticated access and logout CSRF, escaped
categorized flashes, and accessible form errors. The production test also renders
`/` behind the existing forwarded-HTTPS configuration. Existing authentication,
queue, authorization, migration and startup suites remain the regression gate.

Run checks using the documented isolated SQL Server test runner:

```powershell
docker compose run --rm test-runner python -m ruff check .
docker compose run --rm test-runner python -m pytest
```

During implementation, installed headless Chrome rendered the actual Flask pages
at widths 320, 375, 390, 430, 768, 1024, 1280, 1440 and 1920px. Checks covered
horizontal overflow, image loading, control heights and keyboard access to the
skip link. Mobile login/signup and landing screenshots were also reviewed.
This local check did not add a browser dependency or new browser CI requirement.

Validation results: Ruff passed; the full Docker pytest run passed 366 tests and
skipped four optional browser tests because the image has no browser. Those four
existing DOM tests then passed separately using host Chrome. After adding WebP
delivery, the 29 landing/production tests and all nine viewport checks passed again.

Manual follow-up on a running development/staging instance:

1. Open `/` logged out at 320, 390, 768, 1024, 1440 and 1920px. Confirm readable
   headings, wrapped navigation, unclipped artwork/subjects, and no sideways scroll.
2. Tab from the address bar. Activate Skip to content, then exercise Log In,
   Sign Up and Get Started using the keyboard. Check visible focus and 200% zoom.
3. Submit empty authentication fields and check labels, readable error text, and
   focus. Sign up/log in normally; verify the dashboard redirect and protected routes.
4. Visit `/` while logged in, use Open instructor dashboard, Settings and Log out.
5. Start a help session, open its QR/client link in another browser, join, advance,
   leave, and end the session. Check both Master and Client on HTTPS after deployment.
6. Check Safari/iOS and a physical Android browser where available; automated
   rendering here used desktop Chrome, not those engines or physical devices.

Deploy through the existing CI/Azure workflow, including the new blueprint,
templates, stylesheets and artwork in the release commit. No settings or migration
changes are required. Production startup still runs its existing migration gate.

## Milestone 2.3 — Master View

### Layout and shared components

The Master remains the existing owner-protected
`/instructor/sessions/<public_code>/master` endpoint. No route, queue service,
model, database configuration, or deployment setting changed. The repository
uses SQL Server/Azure SQL, rather than PostgreSQL.

`instructor/master.html` owns the persistent heading, presentation toggle, two-column
layout, QR panel, and polite announcement region. `_master_state.html` contains
the replaceable server-authoritative state: serving/next panels, waiting count,
first five waiting entries, actions, and ended state. The current ticket number is
dominant, followed by the optional name. Empty states explain that no student is
serving or waiting. Names remain escaped and wrap without truncation; browser
identifiers never appear in the display.

`master.css` composes existing semantic colors, typography, spacing, radii, focus
and buttons. It introduces `.queue-status`, `.ticket-number`, `.status-label`,
`.queue-count`, `.waiting-list`, `.master-toolbar`, and `.join-panel` within the
Master stylesheet. Keep future Client-specific styles separate; promote patterns
into the shared system only when another view needs them. Landing, authentication,
settings and Client templates are not restyled by this milestone.

### Responsive sizing and the QR

At 64rem (1024px at default font size), content uses two equal grid columns.
The right panel is sticky while the instructor scrolls the waiting list/controls.
The SVG retains its existing square geometry and four-module white quiet zone,
black pattern and white background. Its normal size is the smaller of available
column width and viewport height minus 20rem, with a 16rem lower size bound when
space permits. Presentation mode reduces that height allowance to 12rem. Image
height remains automatic; neither pattern nor quiet zone is cropped or overlaid.
There is no fixed page height and long content can expand naturally.

Below 64rem, status panels appear first, then the QR, then secondary queue details
and controls. The QR can grow to 36rem on portrait tablets. Mobile views scroll
normally rather than squeezing the entire display into one screen. Shared navigation
is compact on the Master and the marketing footer is hidden.

The QR endpoint still requires the owning authenticated instructor and an active
session. It uses `url_for('queue.client', ..., _external=True)` and the request
origin, also shown as the clickable fallback URL. No hostname is hardcoded.
Its image now sits **outside `#live-state`**, so socket invalidations and polling
do not replace it or request/regenerate the SVG. `master-view.js` removes the panel
when an authoritative update reports session end or lost access. A newly loaded
ended page never includes the QR.

### Presentation and instructor actions

Presentation Mode is a local CSS class toggled by a `type="button"` control. It
hides navigation, session metadata, waiting-list details and secondary controls,
and enlarges the ticket/QR space. Done or Serve next remains available so the
instructor can advance the queue while projecting. Exit Presentation Mode and
Escape restore the standard interface. Ending a session or losing access exits
presentation automatically. The mode does not invoke fullscreen, send a request,
write a database value, change queue order, or add an endpoint.

The preference is stored in `sessionStorage`, scoped to this session's Master URL
and tab, so ordinary form navigation restores it. If storage is blocked, the toggle
still works for the current page. Without JavaScript, the toggle stays hidden and
the standard view, QR and POST forms continue to work.

Serve next, Done and End session remain ordinary CSRF-protected POST forms using
the same endpoints, displayed entry IDs and redirect behavior. There was no
existing confirmation modal to replace. Dashboard, Settings, logout and manual
Refresh remain available in standard mode. A successful action still performs the
existing full-page redirect; the QR is fetched once for that new document. This
milestone removes QR reloads from background updates, not from normal navigation.

### Live updates and accessibility

No additional polling loop or socket subscription is added. `master-view.js`
listens to the existing `queue:state` event. `live-updates.js` now also emits
`queue:before-state` immediately before replacement/clearing, allowing focus to
be restored to the same request's control. When that request changes, focus moves
to the status panel rather than a Done button for a different request. Focus also
recovers when an ended/unavailable state removes the currently focused control.

A persistent, polite live region announces a text summary only when serving,
next or waiting information changes. The whole queue is not an ARIA live region.
Connection status writes are deduplicated in the shared updater, avoiding repeated
announcements for identical polls. Student name-draft preservation, serialization,
stale-response rejection, CSRF refresh and authorization failure handling remain
intact. No animations are added; shared reduced-motion and focus conventions apply.

### Tests and display review

`test_master.py` exercises empty/waiting/serving/completed/ended states, read-only
rendering, owner boundaries, exact QR destination and quiet-zone configuration,
and separation of QR from state fragments. Existing tests continue to exercise
actions, stale submissions, escaping, real-time updates, and Client behavior.
`browser_master_view.html` runs through the existing optional browser test runner
and checks toggle/Escape, blocked storage, zero mutation requests from mode changes,
QR node persistence, announcement deduplication, keyboard focus, and QR removal
on session end or authorization loss.

Milestone 2.3 validation: `ruff check .` passed. The full Docker `pytest` run
passed 368 tests and skipped seven optional browser cases because the container
has no browser. All seven browser cases then passed using installed host Chrome,
including the narrow-screen authorization-loss focus regression.

During implementation, Chrome rendered the actual templates with synthetic queue
snapshots at 320×740, 390×844, 430×932, 768×1024, 1024×768, 1280×720, 1440×900,
1920×1080 and 2560×1440 in both modes. QR images loaded, remained square and there
was no horizontal overflow. All three primary elements fit above the fold at
1920×1080 in standard mode and at tested laptop/projector sizes in presentation
mode. Long names, large ticket numbers and 200% text scaling were also checked
without horizontal overflow. Rendering used synthetic data and a stubbed socket;
SQL Server and real-time behavior are covered by the regression suite.

Manual checks on staging/production:

1. Project an active session at 1920×1080 and 2560×1440, then try 1280×720 and
   1440×900. Confirm legibility at the back of the room and scan the QR from several
   physical student phones. Desktop rendering cannot verify camera distance,
   projector contrast, glare or network reachability.
2. Join and leave from two student browsers. Serve next, press Done, and repeat from
   another authorized Master browser. Check numbers/names/counts and the stable QR.
3. Toggle presentation using mouse and keyboard. Press Escape; reload/submit a form
   and verify the tab preference. Test storage denied and JavaScript disabled.
4. At 320–430px and 768px, verify ordering and access to all controls. Try browser
   zoom at 125%, 150% and 200%, unusually long names, and an empty queue.
5. End the session from another Master; confirm the QR disappears and the ended
   message appears. Log out in another tab and confirm a subsequent update clears
   private state and removes the QR. Check screen-reader announcements on actual
   state changes, rather than every poll.

Very long names, unusually large ticket numbers, short windows or increased zoom
may require scrolling; complete readable content takes precedence over forcing a
fixed-height layout. No physical projector, mobile camera, Safari/iOS or screen-reader
device audit was performed. Deploy changed templates, CSS and JavaScript together
through the existing workflow. There are **no new dependencies, configuration
changes, or database migrations**.

## Milestone 2.4 — Client View

### Layout and reusable components

The anonymous student document still extends `queue/base.html`, with a compact
branding header, skip link and footer. It now imports `design-system.css` and
`css/client.css`; it does not inherit instructor navigation. The existing `/session/<code>`
route and Master QR destination are unchanged.

`queue/_client_state.html` arranges three update regions: session context, the
primary ticket/introduction, and secondary details/form. `queue/_ticket.html`
renders the existing ticket number, optional name and preference-aware alert.
`queue/_join_form.html` renders the optional name, associated help/errors and
CSRF-protected join form. Reuse these partials when extending student states.
Do not put queue calculations or identity handling in templates.

The layout uses one column below 48rem (768px at the default font size), then two
columns inside a centered 66rem container. Ticket information comes first in DOM
order. Mobile introductory decoration is omitted to keep the Join action near the
top. Shared panels, button variants, icon/alert macros, typography, status colours,
spacing, corners and focus tokens provide the foundation. Client-specific ticket,
metric, disclosure and layout rules live only in `client.css`; other views are
not restyled. Ticket typography uses `clamp()`, long names/numbers wrap, and
controls allow wrapping with a minimum 48px touch height. Safe-area insets are
respected without disabling browser zoom.

### Supported states and actions

- **Not joined:** “Need a hand?”, session availability, optional name (100-character
  maximum), and Join the Queue. No account, location or additional field is added.
- **Waiting:** prominent ticket, people ahead and the existing estimated-wait
  explanation. Next Up means first waiting request; a student can still have the
  currently served request ahead of them. It does not promise immediate service.
- **Serving:** “It's your turn”, Being helped, and the student's own ticket.
- **Completed / left:** distinct confirmation with an explicit opportunity to
  join again. No automatic rejoin occurs.
- **Ended:** joining/leaving controls disappear; the previous ticket remains
  visible where supplied by the backend, with guidance to obtain a new session link.

The backend supplies no other student's Currently Serving ticket/name, queue title,
help description or paused state, so this view does not invent them. Leave Queue
is inside a native disclosure with an explanation and a destructive POST button;
opening the disclosure changes no queue state. Exit remains read-only. Refresh,
Exit, optional sound/vibration controls and privacy guidance sit outside the live
fragment, so updates retain their state. Existing instructor alert preferences
still control emphasis, announcements, sound and vibration.

### Updates, validation and identity

`client-view.js` enhances ordinary POST forms with Joining/Leaving feedback and a
pending-submission guard. It resets on page restoration or after a stalled navigation
(10 seconds); it never retries a mutation automatically. Backend duplicate-join
protection and validation remain authoritative. Form buttons use wrapping text;
hidden CSRF, browser-binding and entry fields are preserved.

The shared updater offers a cancelable `queue:render` event only for client views.
The client script compares regions for the same status/ticket, retaining unchanged
DOM and refreshing CSRF in place. Changed regions preserve name drafts, invalid-form
feedback (while browser binding matches), open leave disclosures and appropriate
keyboard focus. Status/ticket transitions use the normal complete fragment update.
Focus moves to a readable panel if its control disappears. Master rendering retains
its existing path. No new polling loop, socket connection, storage or API is added.

Existing serialized Socket.IO invalidation reads and 30-second fallback polling
remain in use. Temporary errors retain the displayed state with an update warning;
lost browser access clears it and stops updates. The new polite live region only
announces changed ordinary position/completion/departure/end messages. Next Up,
Serving and advance warnings remain with the existing preference-aware alert
script. Unchanged polling does not repeat those announcements. No motion is added.
`student-alerts.js` also avoids rewriting identical disabled-alert messages in its
status regions; sound/vibration behavior and instructor preferences are unchanged.

The existing signed, HttpOnly browser cookie and server identity mapping are
unchanged. Refresh ordinarily restores the request; clearing/expiring cookies,
changing browsers or blocking cookies can lose access to an existing request.
Shared browsers share a queue identity. The redesign adds no fingerprinting or
personal-data storage. Sound/vibration still require opt-in and browser support;
sleeping/background browsers can miss timely alerts. There is no new push service.

### Validation and manual review

Run `ruff check .` and the existing SQL Server pytest suite. The dedicated Docker
test database is disposable: after restarting its container, run
`docker compose run --rm test-runner python scripts/init_test_database.py` before
`docker compose run --rm test-runner python -m pytest`. Never use a development
or production database. The optional host command
`python -m pytest tests/test_live_browser.py -q` uses installed Chrome/Edge.

Client tests cover anonymous rendering, lifecycle presentations, static assets,
accessible validation and preserved input. Existing join/duplicate/leave/refresh,
authorization, QR, Master, alert and deployment tests remain regression coverage.
`browser_client_view.html` checks selective rendering, token refresh, draft/focus
preservation, retained errors/disclosures, pending submissions, announcements,
temporary error recovery, completion/end and lost-identity clearing.

Milestone 2.4 validation: Ruff passed; the full dedicated SQL Server suite passed
369 tests and skipped eight optional browser cases in the browserless container.
All eight browser cases passed separately in installed host Chrome. After Docker
restarted during verification, its disposable database was reinitialized with the
existing script before repeating the successful full run.

Chrome rendered the actual Flask templates with synthetic snapshots at 320, 375,
390, 430, 600, 768, 1024, 1280, 1440 and 1920px for seven state presentations
(70 combinations). Checks included horizontal overflow, 48px controls, long names,
large ticket numbers, 200% text scaling, server validation and Exit. This used a
stubbed socket and synthetic state, not a browser-to-SQL end-to-end session.

Manual staging checks:

1. Scan the Master QR on physical phones, including Safari/iOS and Android Chrome.
   Try 320–430px, 600–1024px and desktop widths, portrait/landscape, and real browser
   zoom at 200%. Check the software keyboard, pinch zoom and safe areas.
2. Join with a blank name, then with a name. Double-tap Join; refresh and reopen
   the browser. Confirm the same active ticket remains. Test invalid name input.
3. Use two student browsers and a Master: join, leave, Serve next, Done and End
   session. Check counts, Next Up versus Serving, completion and explicit rejoin.
4. Open Leave Queue with keyboard/touch and verify the final button is deliberate.
   Exit and return; confirm it did not cancel the request. Disable JavaScript and
   confirm normal forms and manual Refresh remain usable.
5. Disconnect/reconnect the network. Verify the update warning and recovery.
   With a screen reader, check meaningful announcements and quiet unchanged polls.
   Test optional alerts and instructor-disabled alerts on supported real devices.

Physical devices, screen readers and native browser zoom need manual review;
headless viewport/text-scaling checks cannot establish those behaviors. Deploy
templates and static files together through the existing Azure workflow. There
are **no new dependencies, configuration changes or database migrations**. SQL
Server/Azure SQL, queue services, authentication and anonymous identity are unchanged.

## Milestone 2.5 — Authentication and instructor settings

### Pages and layout

Login and signup share `auth/base.html`, a centered card inside the existing
36rem form container. Branding, a clear heading, brief guidance, required-field
markers, full-width submit buttons and a link to the other authentication page
provide a consistent layout. Signup still collects only display name, email,
password and confirmation. Password guidance matches the existing validator:
15–128 characters, with spaces allowed. Login retains email and password only.
The existing throttled-attempts page uses the same shell and a warning alert;
its HTTP 429 response and Retry-After header are unchanged.

`instructor/base.html` applies the new workspace stylesheet to settings and the
dashboard. The completed Master and Client Views retain their own shells/styles.
Settings remains one POST form with six controls and one Save settings action:

- **When to alert:** Next Up/advance warnings, Currently Serving, and the
  existing 1–3 waiting-request warning distance.
- **How alerts appear:** visual emphasis and permission for students to opt into
  sound or vibration. Descriptions distinguish permission from enabling media.

No control is automatically saved or disabled when another preference changes.
In particular, warning distance is retained when Next Up alerts are off. Status
remains visible to students regardless of alert preferences. Back to dashboard
leads to the existing active Master View link without an additional database query.

The dashboard was the only other instructor administrative screen. Its two cards
present the existing active-session/Start help session action and a settings link.
An active session retains its public code and Open Master View link; no extra
start action is introduced. There are no implemented profile editing, password
reset, account deletion, historical-session or metrics pages, so no placeholder
links or new routes were added.

Forms remain one column. Settings/dashboard cards become two columns at 48rem;
their centered container is capped at 70rem. Page-specific rules in
`css/instructor.css` are scoped to `.instructor-page`. Large text, long names and
button labels wrap; controls have a minimum 48px height and text inputs use at
least 16px type. Increased zoom may require vertical scrolling. Shared navigation
keeps its anonymous/authenticated actions and POST/CSRF logout; current Dashboard,
Settings and Login links receive `aria-current="page"`.

### Shared forms and feedback

The existing tokens, panels, button variants, decorative SVG icons, typography,
flash alerts and focus ring are reused. No new tokens were necessary. Extensions
to `ui/components.html` and `design-system.css` are reusable:

- `field(input, autocomplete='off', help_text='', password_toggle=false)` keeps
  associated labels/error regions and adds required indicators, described help
  and an optional password visibility button. Existing two-argument callers work.
- `choice(input, help_text)` presents a native checkbox inside a large clickable
  label, with separate accessible name, description and error references.
- `form_feedback(form)` displays a generic error summary when validation fails;
  individual fields still display the original backend validation messages.

Non-password inputs and checked values retain server-rendered submitted values
after validation fails. PasswordField's default non-echoing behavior is preserved.
Generic invalid-credential and duplicate-account messages remain unchanged.
Signup/settings success still uses the existing flash mechanism and redirects;
uncategorized flashes retain the shared informational styling. Session expiration
still redirects to login with Flask-Login's existing message. Default CSRF and
HTTP error responses, and the generic database-unavailable response, are unchanged;
no global error-handler redesign was introduced.

### Minimal JavaScript and security boundaries

`instructor-forms.js` is loaded only by the two new page shells. Show/Hide controls
are hidden until enhanced, use `type="button"` and `aria-controls`, and have
action-specific accessible labels. They change only the input type, without
copying, storing, logging or modifying its value. Submission and page departure
conceal revealed passwords. Native password inputs/autocomplete still work without
JavaScript, including paste and password-manager support.

Forms marked `data-submit-feedback` show Signing in / Creating account / Saving
settings / Starting session feedback after native validation. Only the submit
button is disabled, leaving credential, CSRF and preference fields in the native
POST. A duplicate-submission guard resets on page restoration or after 10 seconds
if navigation stalls. It never retries or sends a request itself. Native POST
forms, server validation, rate limits and duplicate-session protection remain
authoritative.

No routes, services, models, validators, authentication rules, ownership checks,
session lifetimes or redirect policies changed. In particular, login still ignores
arbitrary `next` destinations and redirects to the dashboard. There are no new
dependencies, external assets, configuration variables or database migrations.
SQL Server/Azure SQL and Azure startup/deployment assumptions are unchanged.

### Verification and manual checks

Ruff and `git diff --check` passed. The full SQL Server pytest suite passed **374
tests**, with nine optional browser cases skipped in the browserless container.
All **nine Chrome browser cases** passed on the host, including the new instructor
form fixture for required validation, password toggling/concealment, pending
submissions, preserved POST fields and restoration after navigation.

`test_instructor_ui.py` adds template semantics, local assets, password guidance,
retained non-password values, settings error/persistence feedback, dashboard
navigation and the rate-limit recovery page. Existing authentication, logout,
CSRF, ownership, Client, Master, QR and production startup tests remain intact.

Chrome rendered the actual Flask templates at 320, 375, 390, 430, 768, 1024,
1280, 1440 and 1920px for login, signup, settings and both dashboard states,
plus three server-validation error states (48 page/viewport combinations).
Additional checks covered long names, 200% text scaling and no-JavaScript login.
No horizontal overflow was found. These rendering checks used synthetic account,
session and preference data; database-backed behavior is covered by pytest.

Manual staging review:

1. Use physical iOS/Android phones, tablet and desktop browsers. Check narrow
   layouts, the mobile keyboard, autofill/password managers, landscape and native
   browser zoom at 200%. Headless text scaling does not replace these checks.
2. Sign up, submit mismatched passwords, try invalid login, then authenticate and
   log out. Verify clear errors, retained non-password input and empty password
   fields after failed submissions. Use keyboard and a screen reader to operate
   Show/Hide and hear field descriptions and validation feedback.
3. Change all settings, save, reload and confirm persistence. Leave without saving
   to confirm no automatic update. While a session is active, check that students
   receive the instructor's saved alert policy without changing queue order.
4. Test dashboard empty/active states, open the Master View, and scan its QR from
   an anonymous student browser. Confirm existing queue operations still work.
5. Repeat essential forms with JavaScript disabled. Simulate a stalled navigation
   and browser Back to confirm submit controls recover. Check an expired login
   and the existing throttled-attempt message.

No physical-device or screen-reader audit was performed. Deploy the new base
templates, macros, CSS and JavaScript together through the existing Azure workflow.
Keep later account features separate from these presentation components; only
display additional controls after their backend behavior exists.

## Milestone 2.6 — Final quality and consistency

The detailed inventory, findings, test matrix, artifacts, release checklist and
remaining manual checks are in [phase-2-final-qa.md](phase-2-final-qa.md).

### Persistent connection feedback

Master and Client templates now include `_live_status.html` before their queue
content. Keep this single `role="status"` region outside `#live-state`, including
in Presentation Mode. `_live_updates.html` continues to hold configuration and
scripts only. The shared `.connection-status` component uses existing spacing,
muted text and border tokens; `data-state="warning"` uses warning tokens alongside
explicit text explaining that queue data may be stale. Duplicate page-specific
status rules were removed. The status is hidden until JavaScript initializes;
`noscript` supplies manual-refresh guidance without promising a connection.

`live-updates.js` listens for browser offline/online events. Offline reports stale
data immediately and suppresses new reads; online uses the existing serialized
authoritative reader. Fetch failures also label retained data as potentially stale.
The existing Socket.IO connection, 30-second fallback poll, timeout, visibility
reconciliation, stop-on-authorization-loss and deduplicated status text remain.
No additional polling, mutation request, storage or backend state is introduced.

### Reflow and QR sizing

Landing display text and Client alert headings can wrap long words at enlarged
text sizes. Master action buttons cap their minimum/maximum widths at the available
card width, preserving readability at 320px and 200% root text. Normal layouts and
the existing 48rem/64rem breakpoints remain unchanged.

The desktop QR height budget now reserves room for visible connection feedback:
`100svh - 23rem` in standard mode and `100svh - 15rem` in Presentation Mode,
subject to the existing available-width and minimum-size constraints. There is no
fixed page height. At default text and 1920×1080, actual Chrome rendering measured
712px and 840px square QR images respectively, with Currently Serving and Next Up
visible. Smaller/zoomed windows may scroll instead of clipping content.

### Durable QA and maintenance

`tests/test_ui_browser.py` serves actual templates with synthetic service snapshots
over loopback HTTP, using locally installed Chrome/Edge and existing CDP/websocket
dependencies. It never connects to a database. `tests/ui_audit.js` supplies focused
DOM, control-label, ARIA-reference, touch-height, text-contrast and image checks.
The suite renders 24 page states at ten viewports and checks text spacing, enlarged
text, keyboard focus, offline recovery, stable QR and no-JavaScript guidance.
`tests/browser_live_updates.html` additionally exercises failed reads, immediate
offline feedback, recovery and the authorization-loss stop boundary.

Run `python -m pytest tests/test_live_browser.py tests/test_ui_browser.py -q` with
an installed supported browser. Set `UI_QA_ARTIFACT_DIR` to an ignored local directory
to preserve screenshots and JSON measurements. Browser cases remain optional and
skip explicitly when tooling is absent. Continue to run Ruff and the dedicated
SQL Server pytest suite; UI snapshots are not substitutes for backend regressions.

Future changes should reuse the status partial and tokens, keep QR outside live
fragments, and preserve the single authoritative update reader. Do not interpret
focused automated checks as WCAG certification. Real-device keyboards, native zoom,
screen readers, media support and projector scanning remain manual release checks.
No new dependencies, configuration changes or database migrations are required.
