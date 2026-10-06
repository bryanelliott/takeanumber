# CI/CD and Azure operations (Milestone 10)

This prepares deployment; it does not provision Azure resources or deploy them.
Milestone 9 metrics remain unimplemented pending the peak-history decision.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`, and is reused
by deployment. Python 3.13 installs the existing pinned `requirements.txt`, then
runs `pip check`, Ruff, `pytest -m "not browser"`, and a Bash syntax check.
The `browser` marker covers only optional live browser/DOM tests, which are run
manually with `pytest -m browser` and are not part of the deployment gate because
hosted Chromium behavior can cause runner-specific failures. All unit, integration,
database, migration, auth, queue, Socket.IO, and production configuration tests
remain required. PostgreSQL 17 is a disposable
service mapped to `127.0.0.1:55433`. Its database/role are `takeanumber_test`; its
public CI password is not a credential for any persistent database. Existing test
guards, migration round-trips, and actual database/role checks remain in force.
PR jobs receive no deployment secrets or deployment runner access.

Require **Ruff and pytest** in branch protection for `main`. Review workflow
changes and periodically review action versions and full-commit pins. Never execute PR
code with deployment permissions through `pull_request_target`.

## Azure runtime

Provision a Linux Azure App Service with Python 3.13 and Azure Database for
PostgreSQL **Flexible Server** (PostgreSQL 17 matches CI). Use private database
networking, App Service VNet integration, and working private DNS. Provision the
database and roles through platform setup; application tables/indexes/constraints
are created only by Alembic migrations.

Read-only Azure inspection on **2026-10-06** confirmed that the current
`takeanumber-server.postgres.database.azure.com` has public network access
**Disabled**, a delegated subnet in `vnet-bopaypza`, and the private DNS zone
`privatelink.postgres.database.azure.com` linked to that VNet with status Completed.
This is private VNet access, not a public endpoint with a missing firewall rule.
The workflow's standard GitHub-hosted runner has no configured private network
path. Use the manual migration procedure below for this deployment. A working
App Service connection does not give a GitHub runner that network access.
Recheck Portal → PostgreSQL Flexible Server → Networking if infrastructure changes.

Configure the app for **one instance**, with automatic scaling/autoscale disabled.
Do not attach another serving slot to the same live queue. Socket.IO rooms and
authentication limits are process-local; additional workers/instances need a
separate architecture change. No Redis is introduced.

Enable HTTPS Only, minimum inbound TLS 1.2, Always On on a supporting plan, and
`/health` health checks. This endpoint is liveness only, not database readiness.
Set the startup command to **`bash startup.sh`**. The tracked LF-terminated script
launches Gunicorn on `0.0.0.0:8000` with `gthread`, **one worker**, 100 threads, and
a 120-second timeout; `simple-websocket` supplies WebSocket support. Never use
`run.py`, Flask's development server, or migration commands for production startup.

Set `SCM_DO_BUILD_DURING_DEPLOYMENT=true` for App Service/Oryx to build the source ZIP
using `requirements.txt`. Do not enable run-from-package for this source-build
deployment. Verify WebSocket upgrade, polling, and reconnect on the provisioned
Linux app and any upstream proxy.

Required App Service application settings (values configured outside source):

| Name | Value/purpose |
| --- | --- |
| `APP_ENV` | `production`; startup refuses any other value. |
| `SECRET_KEY` | Stable generated secret, at least 32 characters, in protected settings or a Key Vault reference. Rotation invalidates instructor sessions and browser identity cookies. |
| `DATABASE_URL` | Runtime role URL for Flexible Server, with verified TLS; URL-encode credentials. |
| `SESSION_COOKIE_SECURE` | `true`. |
| `TRUSTED_HOSTS` | Comma-separated exact public hostnames. Include the App Service default hostname if used for health checks. No scheme, port, path, or wildcard. |
| `PROXY_FIX_X_FOR` | `0` initially; see proxy verification below. |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true`. |
| `FLASK_DEBUG` | Omit or `0`; never enable in production. |

Existing optional `AUTH_RATE_LIMIT`, `AUTH_RATE_WINDOW_SECONDS`, and
`STUDENT_COOKIE_MAX_AGE` retain defaults of 20, 900, and 15552000 respectively.
Do not set `TEST_DATABASE_URL` in production. `.env` is neither packaged nor loaded
when `APP_ENV=production`. Insecure cookies, testing/debug, short/placeholder
secrets, missing allowed hosts, and unverified database TLS fail validation.

Database URL shape, placeholders only:

```text
postgresql+psycopg://<role>:<URL-encoded-password>@<server>.postgres.database.azure.com/<database>?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt
```

Use the canonical Flexible Server hostname even with private networking. Maintain
the CA bundle on **both** the migration runner and App Service image with the
currently required Microsoft root certificates. A separately maintained PEM bundle
may be used instead. Do not pin leaf/intermediate certificates, disable TLS
verification, or add libpq host/service overrides to the URL. Runtime and migration
URLs must target the same server/database. The migration role needs schema DDL
rights; a separate runtime role needs table access and default grants on future
migration-created objects. Verify those grants after migration. Database password
authentication is independent of App Service publishing credentials.

Production trusts one `X-Forwarded-Proto` hop for App Service TLS termination, but
never forwarded Host/port/prefix. Confirm ingress overwrites the scheme header and
the backend has no public bypass. Client IP forwarding stays untrusted at
`PROXY_FIX_X_FOR=0`, so callers behind that proxy share a rate limit. After verifying
the actual ingress chain, configure the exact trusted client-address hop count
(1–3 supported) and test that a forged incoming `X-Forwarded-For` cannot select the
effective address. Reassess when adding Front Door or another proxy. Verify HTTPS
QR URLs, secure cookies, CSRF, and same-origin Socket.IO on the deployed hostname.

## GitHub environment and publish profile

Create the **`production`** environment with required reviewers, prevent self-review
where supported, and restrict deployments to protected `main`. If the repository
plan cannot enforce those controls, establish an equivalent approval gate before
enabling deployment. Deployment is manual, accepts no arbitrary source ref, reruns
CI on the selected main commit, and serializes runs without cancelling migrations.

In the Azure portal, enable **SCM Basic Auth Publishing Credentials** for the target
app and download its production publish profile. For Linux, set
`WEBSITE_WEBDEPLOY_USE_SCM=true` before downloading if required by the portal.
Store the complete XML contents as the `production` environment secret
`AZURE_WEBAPP_PUBLISH_PROFILE`. Treat it as a password: never commit it, include it
in artifacts, or print it; rotate/reset publishing credentials and replace the
secret when needed. FTP publishing is not needed. If platform policy disables SCM
basic authentication, an administrator must allow it before this method can work.

The workflow uses `azure/webapps-deploy@v3` with that profile. It needs no Azure CLI
installation or authenticated Azure session. Configure the Python stack and
**`bash startup.sh`** startup command in the portal before approving deployment;
the action's `startup-command` input is unsupported with publish profiles.
The preflight script reads SCM `/api/settings` using the same profile, requires
`SCM_DO_BUILD_DURING_DEPLOYMENT=true`, and rejects run-from-package. It fails closed
on authentication/network errors without printing credentials or settings.

Required GitHub configuration (exact names consumed by the workflow):

| Scope/type | Name | Purpose |
| --- | --- | --- |
| Repository variable (optional) | `AZURE_DEPLOY_RUNNER_LABELS` | JSON array selecting an isolated ephemeral Linux deployment runner, e.g. `["self-hosted", "linux", "x64", "azure-deploy"]`. Defaults to `["ubuntu-24.04"]`; repository scope is required for runner selection. |
| `production` variable | `AZURE_WEBAPP_NAME` | Existing target web app name. |
| `production` variable | `APP_HEALTH_URL` | Exact target HTTPS URL ending in `/health`. |
| `production` variable | `APP_TRUSTED_HOSTS` | Same host list as runtime `TRUSTED_HOSTS`, for the CLI factory. |
| `production` variable | `MIGRATION_DATABASE_NETWORK` | `private` (default and current deployment). Use `public` only after verifying that the server really exposes public access and the runner is allowed through its firewall. |
| `production` secret | `AZURE_WEBAPP_PUBLISH_PROFILE` | Complete production App Service publish-profile XML. |
| `production` secret | `MIGRATION_DATABASE_URL` | DDL-capable URL with verified TLS; same server/database as runtime. |

Runtime signing/database secrets live in App
Service or Key Vault references, not ZIPs. The migration CLI generates a temporary
signing key because it serves no requests; never reuse it as the runtime key.

The migration command requires only Python 3.13, application dependencies, current
CA certificates, the production configuration below, and network/DNS access to
Flexible Server (normally TCP 5432). It authenticates directly using the database
password in `MIGRATION_DATABASE_URL`, mapped to `DATABASE_URL` for the CLI.
This mapping is intentional: the app factory reads `DATABASE_URL`, not
`MIGRATION_DATABASE_URL`. The GitHub secret must contain the **migration role**
with schema DDL privileges and ownership/membership needed to alter existing
objects, not the restricted App Service runtime role. GitHub masks the value, so
`DATABASE_URL=***` confirms neither which role it contains nor its privileges.
Verify or replace that secret from the approved credential store; its saved value
cannot be read back through GitHub. Do not grant DDL to the runtime role to fix this.

The migration job uses checkout/setup-python and Bash to prepare that command;
it has no publish-profile input or Azure authentication step. The separate
deployment job also uses Git, Bash, curl, setup-python, and HTTPS
access to App Service SCM, GitHub, package downloads, and the public health URL.
GitHub-hosted runners work only when the database firewall/routing permits them.
They cannot normally resolve/reach a private Flexible Server endpoint. Use an
isolated ephemeral runner with private DNS/routing, or the manual procedure below;
do not expose a private database just to make this workflow pass. Restrict any
self-hosted runner group to trusted deployment workflows, never PR code or
untrusted repositories, and recreate runners after each job. CI always uses
GitHub-hosted Ubuntu and its disposable database.

The workflow now defaults to **manual** migration. In explicit `runner` mode,
`scripts/check_migration_inputs.py` rejects private networking on a standard
GitHub-hosted runner before installing dependencies or connecting. A self-hosted
runner must still have verified DNS/routing; its label alone proves no connectivity.
Do not set `MIGRATION_DATABASE_NETWORK=public` to bypass this check for a private
server. There are no automatic connection retries or fallback migrations.

`.github/workflows/deploy.yml` is the sole deployment workflow. The portal-generated
push deployment has been removed because it bypassed CI, environment approval,
and migrations. Do not re-enable it through Deployment Center.

## Release and migration procedure

1. Review the exact commit/migrations, CI results, currently deployed revision,
   and runtime/migration database targets. Verify a recent restorable Flexible
   Server backup/PITR window and test the change and recovery plan on a restored
   nonproduction database with representative volume.
2. This workflow requires **backward-compatible, transactional, expand-first
   migrations**: the old application stays live during migration. Dropping/renaming
   columns, lengthy backfills, autocommit, and `CREATE INDEX CONCURRENTLY` require
   a separately reviewed maintenance procedure. Do not approve the routine path
   for them. End live help sessions before disruptive maintenance.
3. Dispatch **Deploy Azure production** from `main`. After that SHA passes CI,
   the environment reviewer confirms the preparation above before allowing the
   migration job. Both migration and deployment jobs use the protected environment.
   For the current private server, first perform the manual procedure below, then
   use `migration_mode=manual` (the default) with its recorded `migrated_sha`.
   Use `runner` with an empty `migrated_sha` only on a verified network path.
   Review queued runs to avoid deploying an obsolete commit.
4. In runner mode, the migration job installs dependencies and runs
   `python -m flask --app app:create_app deploy-upgrade` with the protected
   `MIGRATION_DATABASE_URL` secret; no Azure login is involved in migrations.
   This command holds transaction advisory lock `20261001`, sets a 5-second DDL
   lock timeout and 120-second per-statement timeout, runs Alembic on the same
   connection/outer transaction, and checks the resulting single migration head.
   Competition, timeout, failure, or revision mismatch blocks code deployment and
   rolls back transactional changes. All production migration operators must use
   this command to cooperate with the lock. Never use `db stamp` to disguise a
   mismatch, and never migrate in web-process startup hooks.
   `db.create_all()` and direct `flask db upgrade` are not production migration
   paths; `deploy-upgrade` is the only supported production migration command.
   In manual mode, the job verifies the attested SHA matches the release; it does
   not connect to PostgreSQL or run migrations again.
5. Only after migration approval/success does the deployment job check build
   automation with the publish profile. Only tracked `app/`, `migrations/`,
   `requirements.txt`, and `startup.sh` from the
   tested SHA enter the source ZIP. `.env`, `.git`, tests, local virtual environments,
   and runner secrets are excluded. App Service builds and deploys this package.
6. The job checks `/health`. Then verify database-backed login, ownership checks,
   session start/end, HTTPS QR Client View, and two-browser Socket.IO updates.
   Confirm the commit in App Service deployment history. Liveness alone cannot
   establish database readiness or that the right release is serving.

If migration fails, code deployment does not run. Review the database revision
before retrying. If build preflight/deployment/health checks fail **after** migration, the schema
may already be upgraded. Restore the previous compatible application artifact or
roll forward after review; never automatically downgrade schema or retry against
another database. Database restore requires the Flexible Server recovery procedure
and may require coordinated configuration changes and downtime. Never run pytest
against production or the migration database.

## Manual migration for private database networking

**Use this procedure for the current private Flexible Server.** The trusted
machine needs private network/VPN connectivity, working private DNS for the
canonical server hostname, Python 3.13, application dependencies, and current CA
roots. No App Service publish profile or Azure authentication is needed there.

1. Complete the backup, compatibility, target-database, and CI review above for
   the exact release commit on protected `main`. Coordinate with other operators:
   allow no competing release between the manual migration and code deployment.
   The database advisory lock covers the migration transaction, not that interval.
2. On the trusted machine, check out that exact full commit SHA in a clean release
   directory. Create/activate an isolated Python environment and install
   `requirements.txt`; run `python -m pip check`. Supply the same protected migration
   database credential through an approved secret channel. GitHub environment
   secrets cannot be downloaded after saving them; retain the credential in your
   approved secret store. Do not paste it into command history, logs, or source.
3. In a Bash session with `MIGRATION_DATABASE_URL` securely injected, run:

   ```bash
   set -euo pipefail
   set +x
   python3.13 -m venv .migration-venv
   source .migration-venv/bin/activate
   python -m pip install -r requirements.txt
   python -m pip check
   export APP_ENV=production FLASK_SKIP_DOTENV=1 FLASK_DEBUG=0
   export SESSION_COOKIE_SECURE=true PROXY_FIX_X_FOR=0
   export TRUSTED_HOSTS='<same comma-separated hostnames as App Service>'
   export DATABASE_URL="${MIGRATION_DATABASE_URL:?Supply the protected migration URL}"
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   unset TEST_DATABASE_URL
   python -m flask --app app:create_app check-db
   python -m flask --app app:create_app deploy-upgrade
   unset DATABASE_URL MIGRATION_DATABASE_URL SECRET_KEY
   ```

   Use a CA bundle path valid on this machine in `sslrootcert`, keeping
   `sslmode=verify-full` and the same server/database/role. The temporary signing
   key serves only this CLI process. A nonzero exit means **stop**; do not deploy.
   The same lock, transaction, timeouts, and migration-head checks run here.
   `check-db` is read-only: success verifies connection/TLS/authentication, not DDL
   privileges or a migrated schema. Only a successful `deploy-upgrade` counts as
   migration evidence. Use a VM on the linked VNet or an approved VPN/peered network
   with working DNS; a normal Cloud Shell or workstation is not automatically on it.
4. Record the full commit SHA, successful exit and `Database upgraded to the release
   head.` message, database target (without credentials), operator, and time in the
   protected release record. Close the credential-bearing shell even after failure.
5. Dispatch **Deploy Azure production** from `main` with `migration_mode=manual`
   and `migrated_sha` equal to that full SHA. The workflow reruns CI and rejects a
   SHA different from its tested `github.sha`. If `main` has advanced, stop and
   review/migrate the new release; do not substitute an unverified SHA.
6. Before approving the `production` environment, the reviewer must verify that
   migration evidence and database target match this release, and that no other
   migration intervened. Manual mode skips the runner's migration step; the SHA
   check is an attestation check, not a remote database readiness check. Missing or
   failed migration evidence must block approval. The build preflight, tracked-file
   packaging, publish-profile deployment, and health checks still run normally.

There is no automatic fallback to manual mode on migration failure. If SCM also
uses private access restrictions, deployment still needs a runner that can reach
SCM; manual database migration does not bypass those restrictions.

## Safe failure diagnostics and public-network troubleshooting

`check-db` and `deploy-upgrade` print a fixed failure category and action hint.
They never print the database URL, user/password, SQL, bound parameters, signing
key, driver error text, or traceback. SQLSTATE is used where available; connection
failures without SQLSTATE use known libpq message patterns in memory only. An
unrecognized connection failure remains `database-connection`, not a guessed cause.

| Category | Action before retrying |
| --- | --- |
| `dns-resolution` | Verify the canonical PostgreSQL hostname. On private networks verify the DNS zone link and VPN/peering DNS forwarding. A DNS error alone does not prove networking mode; verify it in the portal. |
| `network-timeout` / `database-connection` | Check server readiness, port 5432 routing, firewall and outbound access. Do not retry the current private server from a standard GitHub-hosted runner. |
| `tls-verification` | Keep `sslmode=verify-full`. Use a readable CA bundle at the `sslrootcert` path on the migration machine, containing current trusted roots; use the canonical hostname, not an IP. |
| `postgres-authentication` | Verify password authentication is enabled and the migration role/password is current. URL-encode credential components; never paste the URL into logs. |
| `database-privileges` | Have the database administrator verify CONNECT, schema USAGE/CREATE, and ownership or role membership for ALTER operations and the Alembic version table. Runtime DML permissions alone are insufficient. No application objects should be created manually. |
| `network-access-policy` | PostgreSQL rejected access through its host/network policy. Review authorized network/firewall settings; do not enable broad public access. |
| `migration-timeout` | Review contention or long statements; the existing 5-second DDL lock and 120-second statement limits remain enforced. |
| `alembic-migration` | Review the checked-out migration chain and existing database revision using protected operator tooling. Do not stamp, auto-downgrade, or recreate tables. |

If the server is deliberately changed to **public** networking later, confirm that
mode in the portal, authorize the runner's actual outbound address through the
database firewall, and set `MIGRATION_DATABASE_NETWORK=public` before selecting
`runner`. Prefer a runner with a controlled egress address over broad firewall
exceptions. Check TLS, credentials and DDL-role privileges using the categories
above; do not treat changing to public access as a fix for an authentication error.

The observed old generic failure cannot reveal whether libpq failed at DNS or
connect time. The confirmed private-network/hosted-runner mismatch must be fixed
first. Role privileges and the masked GitHub migration secret remain operator
checks; successful network access does not establish that those values are correct.

## Logging and validation limits

Gunicorn access logging remains off by default; error logs use warning level.
SQLAlchemy hides bound parameters, and migration failures avoid printing sensitive
exceptions. Do not enable SQL echo, request body/cookie capture, shell tracing, or
verbose credential/SCM HTTP logging. The SCM preflight prints only its status.
Application Insights instrumentation is not added. If enabling platform diagnostics,
review access/retention and collect operational status, duration, and sanitized
errors only; avoid names, browser identifiers, cookies, bodies, connection strings,
and IP/geolocation enrichment. No student location collection is added.

Local validation checks workflow syntax, Bash syntax, configuration, and migration
transactions on the dedicated test database. Publishing credentials, SCM access, private
routing, CA trust, Oryx builds, and real WebSockets require provisioned-environment
verification. Repository preparation does not dispatch workflows or mutate Azure.

References: [App Service GitHub deployment and publish profiles](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions),
[Web Apps Deploy action limitations](https://github.com/Azure/webapps-deploy),
[SCM settings API](https://github.com/projectkudu/kudu/wiki/REST-API#settings),
[Flexible Server private networking](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private),
[Python App Service configuration](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python),
[Flexible Server TLS](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect),
and [Flask-SocketIO deployment](https://flask-socketio.readthedocs.io/en/latest/deployment.html).
