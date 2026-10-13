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
that layout. Its CSS lives in `master.css`. The independent student `queue/base.html`, queue layouts,
alert emphasis, and real-time scripts are unchanged; their dedicated redesign is
future work.

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
