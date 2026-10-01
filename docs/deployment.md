# CI/CD and Azure operations (Milestone 10)

This prepares deployment; it does not provision Azure resources or deploy them.
Milestone 9 metrics remain unimplemented pending the peak-history decision.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`, and is reused
by deployment. Python 3.13 installs the existing pinned `requirements.txt`, then
runs `pip check`, Ruff, pytest, and a Bash syntax check. PostgreSQL 17 is a disposable
service mapped to `127.0.0.1:55433`. Its database/role are `takeanumber_test`; its
public CI password is not a credential for any persistent database. Existing test
guards, migration round-trips, and actual database/role checks remain in force.
PR jobs receive no Azure secrets, OIDC permissions, or deployment runner access.

Require **Ruff and pytest** in branch protection for `main`. Review workflow
changes and periodically update the full-commit action pins. Never execute PR
code with deployment permissions through `pull_request_target`.

## Azure runtime

Provision a Linux Azure App Service with Python 3.13 and Azure Database for
PostgreSQL **Flexible Server** (PostgreSQL 17 matches CI). Use private database
networking, App Service VNet integration, and working private DNS. Provision the
database and roles through platform setup; application tables/indexes/constraints
are created only by Alembic migrations.

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
migration-created objects. Verify those grants after migration. OIDC below covers
the Azure control plane, not PostgreSQL authorization.

Production trusts one `X-Forwarded-Proto` hop for App Service TLS termination, but
never forwarded Host/port/prefix. Confirm ingress overwrites the scheme header and
the backend has no public bypass. Client IP forwarding stays untrusted at
`PROXY_FIX_X_FOR=0`, so callers behind that proxy share a rate limit. After verifying
the actual ingress chain, configure the exact trusted client-address hop count
(1–3 supported) and test that a forged incoming `X-Forwarded-For` cannot select the
effective address. Reassess when adding Front Door or another proxy. Verify HTTPS
QR URLs, secure cookies, CSRF, and same-origin Socket.IO on the deployed hostname.

## GitHub environment and OIDC

Create the **`production`** environment with required reviewers, prevent self-review
where supported, and restrict deployments to protected `main`. If the repository
plan cannot enforce those controls, establish an equivalent approval gate before
enabling deployment. Deployment is manual, accepts no arbitrary source ref, reruns
CI on the selected main commit, and serializes runs without cancelling migrations.

Create an Entra application/service principal or user-assigned identity with:

| Federated credential field | Value |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Subject | `repo:<owner>/<repository>:environment:production` |
| Audience | `api://AzureADTokenExchange` |

Grant Website Contributor **at the target web app scope**, or a narrower reviewed
custom deployment/configuration-read role. Do not grant subscription Owner.
Provisioning and database permissions are separate operator tasks. Only the deploy
job has `id-token: write`; Azure Login exchanges that token for short-lived Azure
access. No client secret, publish profile, or `AZURE_CREDENTIALS` JSON is used.

Required GitHub configuration (exact names consumed by the workflow):

| Scope/type | Name | Purpose |
| --- | --- | --- |
| Repository variable | `AZURE_DEPLOY_RUNNER_LABELS` | JSON array selecting an isolated ephemeral Linux deployment runner, e.g. `["self-hosted", "linux", "x64", "azure-deploy"]`. Repository scope is required for runner selection. |
| `production` variable | `AZURE_WEBAPP_NAME` | Existing target web app name. |
| `production` variable | `AZURE_RESOURCE_GROUP` | App's resource group. |
| `production` variable | `APP_HEALTH_URL` | Exact target HTTPS URL ending in `/health`. |
| `production` variable | `APP_TRUSTED_HOSTS` | Same host list as runtime `TRUSTED_HOSTS`, for the CLI factory. |
| `production` secret | `AZURE_CLIENT_ID` | Federated Entra application/identity client ID. |
| `production` secret | `AZURE_TENANT_ID` | Entra tenant ID. |
| `production` secret | `AZURE_SUBSCRIPTION_ID` | Target subscription ID. |
| `production` secret | `MIGRATION_DATABASE_URL` | DDL-capable URL with verified TLS; same server/database as runtime. |

The three Azure IDs identify federation, not passwords; environment secrets match
Azure Login's recommended inputs. Runtime signing/database secrets live in App
Service or Key Vault references, not ZIPs. The migration CLI generates a temporary
signing key because it serves no requests; never reuse it as the runtime key.

The deployment runner needs Azure CLI, Git, Bash, curl, Python 3.13/setup-python
support, current CA roots, and network/DNS access to Flexible Server, Azure control
plane, App Service SCM, GitHub, and package downloads. Restrict its runner group to
trusted deployment workflows, never PR code or untrusted repositories. Recreate
the runner after each job; do not retain release environments/credentials on a
shared host. CI always uses GitHub-hosted Ubuntu and its disposable database.

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
   deployment job. Review queued runs to avoid deploying an obsolete commit.
4. The job installs dependencies, authenticates through OIDC, checks build
   automation, and runs `python -m flask --app app:create_app deploy-upgrade`.
   This command holds transaction advisory lock `20261001`, sets a 5-second DDL
   lock timeout and 120-second per-statement timeout, runs Alembic on the same
   connection/outer transaction, and checks the resulting single migration head.
   Competition, timeout, failure, or revision mismatch blocks code deployment and
   rolls back transactional changes. All production migration operators must use
   this command to cooperate with the lock. Never use `db stamp` to disguise a
   mismatch, and never migrate in web-process startup hooks.
5. Only tracked `app/`, `migrations/`, `requirements.txt`, and `startup.sh` from the
   tested SHA enter the source ZIP. `.env`, `.git`, tests, local virtual environments,
   and runner secrets are excluded. App Service builds and deploys this package.
6. The job checks `/health`. Then verify database-backed login, ownership checks,
   session start/end, HTTPS QR Client View, and two-browser Socket.IO updates.
   Confirm the commit in App Service deployment history. Liveness alone cannot
   establish database readiness or that the right release is serving.

If migration fails, code deployment does not run. Review the database revision
before retrying. If deployment/health checks fail **after** migration, the schema
may already be upgraded. Restore the previous compatible application artifact or
roll forward after review; never automatically downgrade schema or retry against
another database. Database restore requires the Flexible Server recovery procedure
and may require coordinated configuration changes and downtime. Never run pytest
against production or the migration database.

## Logging and validation limits

Gunicorn access logging remains off by default; error logs use warning level.
SQLAlchemy hides bound parameters, and migration failures avoid printing sensitive
exceptions. Do not enable SQL echo, request body/cookie capture, or verbose Azure
CLI output. CLI output is suppressed except the nonsecret build flag query.
Application Insights instrumentation is not added. If enabling platform diagnostics,
review access/retention and collect operational status, duration, and sanitized
errors only; avoid names, browser identifiers, cookies, bodies, connection strings,
and IP/geolocation enrichment. No student location collection is added.

Local validation checks workflow syntax, Bash syntax, configuration, and migration
transactions on the dedicated test database. Azure federation, RBAC, private
routing, CA trust, Oryx builds, and real WebSockets require provisioned-environment
verification. Repository preparation does not dispatch workflows or mutate Azure.

References: [Azure OIDC deployment](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions),
[Azure Login](https://github.com/Azure/login),
[Python App Service configuration](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python),
[Flexible Server TLS](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect),
and [Flask-SocketIO deployment](https://flask-socketio.readthedocs.io/en/latest/deployment.html).
