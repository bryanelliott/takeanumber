# Azure SQL deployment and operations

## Release architecture

Infrastructure can be provisioned with [Terraform](../infra/README.md). That guide
documents an optional initial administrator-credential bootstrap and switching both
runtime and migrations together to a contained application user. The Portal procedure
below uses the recommended contained user from the start. Both use one application
`DATABASE_URL`; Terraform never executes SQL or migrations.

The normal release is **CI -> publish-profile deploy -> App Service `deploy-upgrade`
using `DATABASE_URL` -> Gunicorn**. Use Azure App Service Linux, Python 3.13,
one App Service instance and one threaded Gunicorn worker. The database is Azure
SQL Database, optionally General Purpose Serverless with auto-pause.

GitHub never connects to the production database. It runs Ruff and all required
pytest tests in disposable SQL Server 2022/Python 3.13/ODBC Driver 18 containers.
Only the optional `browser` tests are excluded (`pytest -m "not browser"`);
`pytest -m browser` runs those manually. Database, migration, authentication,
queue, settings, Socket.IO and production configuration tests remain mandatory.

There is one application database user and one App Service `DATABASE_URL` for
both migrations and requests. SQL password authentication and the App Service
publish profile require no Azure CLI login, service principal, OIDC, or Entra
integration. No migration machine or database access from GitHub is needed.

## 1. Create the empty Azure SQL database

In Azure Portal:

1. Create **SQL database**, named `takeanumber`, in the App Service region.
2. Create/select an **Azure SQL logical server**. Enable SQL authentication and
   create a provisioning administrator with a generated password. Do not enable
   an Entra-only authentication policy. The provisioning administrator is used
   only for resource/user setup; it is never the application's credential.
3. Under **Compute + storage**, choose General Purpose Serverless if desired.
   Review region availability, minimum/maximum vCores, storage and auto-pause
   delay/cost before creating the resource. Start with a blank database, no sample data.
4. Under server **Networking**, enable public access for **Selected networks**.
   Add each outbound IP address required by App Service (App Service -> Properties ?
   Outbound IP addresses and Additional outbound IP addresses). Add only the
   administrator's current client IP temporarily for setup. Leave **Allow Azure
   services and resources to access this server** disabled; it is broader than this app.
5. App Service must resolve `<server>.database.windows.net` and reach TCP 1433.
   Set the logical server **Connection policy** to **Proxy** for the simplest
   outbound firewall policy. Redirect policy instead requires the documented
   additional regional SQL ports. Verify any existing VNet integration, route-all,
   NSG/firewall and DNS settings permit this new endpoint. No private DNS is needed.
6. Keep the server's minimum TLS version at least 1.2. Leave certificate
   validation enabled in the application. Review backup retention and restore
   requirements for the application's data.

This change does not provision Azure resources, copy data, or delete the previous
database. Start with a **new empty database**. The initial baseline is not an
upgrade path from the retired database engine or its migration revisions.

## 2. Create the single application database user

Open the database's **Query editor** with SQL authentication as the provisioning
administrator, or use an authorized SQL client with encrypted, verified TLS.
Connect **directly to `takeanumber`, not `master`**. Execute once, replacing the
password placeholder with a generated strong secret (escape `'` as `''` in SQL):

```sql
CREATE USER [takeanumber_app]
    WITH PASSWORD = '<generated-application-password>', DEFAULT_SCHEMA = [dbo];
GRANT CONNECT, CREATE TABLE TO [takeanumber_app];
GRANT CONTROL ON SCHEMA::[dbo] TO [takeanumber_app];

SELECT DB_NAME() AS database_name,
       is_read_committed_snapshot_on
FROM sys.databases WHERE name = DB_NAME();
```

Azure SQL supports a contained SQL user with a password; no separate server login
or identity integration is necessary. Remove the temporary administrator firewall
rule when setup is complete. Protect this one application password in App Service.

The database is dedicated to this application. `CONTROL` on `dbo` grants SELECT,
INSERT, UPDATE, DELETE, REFERENCES, ALTER and metadata access to current and future
schema objects, including indexes, constraints and `alembic_version`. Database
`CREATE TABLE` permits Alembic to create tables in that schema. These grants allow
first initialization and future table/index/constraint migrations without
`db_owner`, server administration, or user-management rights. A future migration
introducing views/procedures/types needs its corresponding CREATE permission
reviewed explicitly; the current schema contains none.

`sp_getapplock` uses `@DbPrincipal='public'`; every database user belongs to public,
so no additional elevated lock permission is required. Both app and migration use
the same user. CI provisions an equivalent non-owner test user and exercises these
permissions, including DDL, DML and migration locking.

Azure SQL normally enables READ_COMMITTED_SNAPSHOT. The SELECT above must return
`1`; local tests enable it explicitly. If an existing database returns `0`, the
provisioning administrator should enable it before any application sessions open:

```sql
ALTER DATABASE [takeanumber] SET READ_COMMITTED_SNAPSHOT ON;
```

See [contained SQL users](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql),
[schema permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-schema-permissions-transact-sql)
and [application locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql).

## 3. Configure App Service

In **Configuration -> General settings**, select Linux / Python 3.13, startup
command **`bash startup.sh`**, enable WebSockets, and keep one App Service instance.
Use HTTPS Only, a minimum TLS version of 1.2 or newer, and HTTP/2 as supported.
Disable FTP publishing. Enable **SCM Basic Auth Publishing Credentials** for the
publish-profile deployment; restrict access to the profile. No Azure login action
is used. Avoid an alternate portal-generated deployment workflow that bypasses CI.

In **Environment variables -> App settings**, configure:

| Setting | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | The one SQLAlchemy URL shown below |
| `SECRET_KEY` | Stable randomly generated secret, at least 32 characters; e.g. 32 random bytes as hex |
| `SESSION_COOKIE_SECURE` | `true` |
| `TRUSTED_HOSTS` | Exact comma-separated public hostnames, no scheme, paths or wildcards |
| `FLASK_SKIP_DOTENV` | `1` (also exported by startup) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (required for ZIP dependency installation) |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `600` seconds to allow resume, migration and startup |
| `PROXY_FIX_X_FOR` | `0` initially; change only after verifying the trusted ingress chain |

Do not enable Flask debug/testing or install `TEST_DATABASE_URL` in production.
Existing optional `AUTH_RATE_LIMIT` (20), `AUTH_RATE_WINDOW_SECONDS` (900), and
`STUDENT_COOKIE_MAX_AGE` (15552000 seconds) retain their defaults and validation.
App Service terminates HTTPS; the app trusts one forwarded scheme header and
never trusts a forwarded Host header. Verify client IP handling before opting into
forwarded client-address trust, particularly when a gateway/CDN is added.

Use a normal **App setting**, not the Portal's typed SQL connection-string field:

```text
mssql+pyodbc://takeanumber_app:<URL-encoded-password>@<server>.database.windows.net:1433/takeanumber?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
```

Percent-encode the username/password components, particularly `@`, `:`, `/`, `%`,
`?`, `#` and `&`. Use the canonical server hostname, not an IP address. Store the
complete URL only in the protected setting; never echo it, paste it into a workflow
or include it in support logs. The application accepts only these three URL query
options, requires Driver 18 and encryption, and rejects certificate bypass in
production. It adds `ConnectRetryCount=0` itself to avoid hidden driver retry loops.
The `TrustServerCertificate=yes` examples elsewhere are exclusively for local
self-signed SQL Server containers, never Azure production.

Microsoft ODBC Driver 18 and trusted CA roots must be installed in the Linux runtime;
`pip install pyodbc` alone does not install the native driver. The built-in App Service
Linux Python images commonly include ODBC drivers, but verify **Driver 18** in the
actual Python 3.13 image via Portal SSH before the first release:

```bash
odbcinst -q -d
```

Startup also verifies Driver 18 through pyodbc and fails closed if missing. Do not
silently fall back to Driver 17 or unverified TLS. If the chosen runtime image lacks
18, resolve its native-driver installation using Microsoft's supported image/package
instructions before release. The test image installs Driver 18 explicitly. Native
package installation is an environment prerequisite, not a recurring migration step.
See [App Service ODBC availability](https://learn.microsoft.com/en-us/sql/connect/python/mssql-django/deploy-azure-app-service)
and [Linux Driver 18 installation](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server).

Set App Service Health check to **`/health`**. It reports process liveness only and
never opens a database connection, including requests with an instructor cookie.
It is not a database readiness check. Always On can keep the web process warm;
database-touching synthetic checks must not be used if auto-pause is desired.

## 4. Configure GitHub once

Create/protect the GitHub environment **`production`** with required reviewers and
main-only deployment rules where supported. Require the CI **Ruff and pytest
(SQL Server)** job for merging. Set:

| Kind | Name | Value |
| --- | --- | --- |
| Environment secret | `AZURE_WEBAPP_PUBLISH_PROFILE` | Complete App Service publish-profile XML |
| Environment variable | `AZURE_WEBAPP_NAME` | Target App Service name |
| Environment variable | `APP_HEALTH_URL` | `https://<trusted-app-host>/health` |

Download the profile in Portal after enabling SCM basic auth. Treat the XML as a
credential; rotate/re-download it when publishing credentials change. The workflow
uses `azure/webapps-deploy@v3`. Its SCM preflight verifies remote build automation;
release ZIPs contain only tracked runtime files from the exact tested commit.
The production database URL is **not** a GitHub secret or workflow input.
Remove obsolete deployment inputs, database secrets and runner/network variables
from the environment; only the table above is used now.

## 5. First deployment to the empty database

1. Finish database/user/firewall provisioning and App Service settings above.
   Confirm the database contains no application tables or old Alembic history.
2. Commit the reviewed SQL Server baseline and all port changes. Push to GitHub
   and require CI to pass against its disposable database.
3. Open Actions -> **Deploy Azure production** -> Run workflow -> **main**. Approve
   the protected deployment after reviewing the exact commit. There are no
   migration-mode or migration-record inputs.
4. GitHub deploys the ZIP with the publish profile. App Service installs pinned
   dependencies, then runs `bash startup.sh` using its own settings and network.
5. Startup validates required environment settings and Driver 18, invokes
   `python -m flask --app app:create_app deploy-upgrade`, and creates all five
   application tables plus the Alembic version table through revision
   **`0001_sqlserver_baseline`**. Only a successful migration starts Gunicorn.
6. Inspect protected App Service startup logs for **Database upgraded to the release
   head**. Verify `/health` returns `{"status":"ok"}`; then test instructor signup/login,
   create a session, join from a separate browser, advance/leave/end, save settings,
   and check cross-browser Socket.IO updates. This verifies DB access beyond liveness.

No administrator-created application tables, `db.create_all()`, migration host or
separate manual migration command is required. The Python app factory never creates
or upgrades a schema; only the explicit deployment wrapper owns production migrations.

## 6. Normal future deployments and migration safety

Commit code and any reviewed Alembic revision together, pass CI, then dispatch and
approve the main-branch deployment as above. App Service startup automatically
runs the wrapper on **every restart** as well as deployment. Already-at-head upgrades
are harmless, still locked and verified. GitHub requires no DB credentials or access.

The wrapper checks for exactly one release head before connecting. It acquires the
exclusive database-scoped `TakeANumber:deploy-upgrade` application lock with
`sp_getapplock`, owned by the same physical transaction Alembic uses. Competing
migration attempts fail promptly rather than running together. Connection opening
has bounded serverless-resume retries; migrations use a 5-second SQL lock timeout,
a 120-second per-statement ODBC query timeout and `XACT_ABORT ON`. The wrapper verifies
the final Alembic heads exactly equal the release head before commit. SQL Server
transactional DDL rolls back with the revision record on any failure. Lock release
follows commit/rollback/connection close. Failure exits nonzero and Gunicorn cannot start.

Review future revisions for SQL Server support, filtered indexes, named constraints,
transactional DDL and a practical downgrade. Do not put commits, separate engine
connections or Alembic autocommit blocks in production migrations: these would
escape transaction ownership and release the application lock early. Long data
backfills require a separately reviewed design and cannot be hidden in routine startup.

Use backward-compatible migrations while the previous release may still serve
requests. One configured worker does not eliminate old/new process overlap during
platform replacement. The migration lock serializes migrations, not all application
traffic. Schedule a maintenance window for incompatible changes. Confirm backups
and a restore plan before destructive changes. Do not automatically downgrade on
failure. A rollback to an older code version with a different head deliberately
fails validation; use a reviewed forward fix or restore compatible code and DB
state together. Never restore the retired migration chain onto this new database.

`/health` succeeding during deployment can temporarily come from the previous process.
Check new-release startup logs and functional behavior before declaring a release
successful. A failed new process may leave the previous release serving or the site
unavailable, depending on App Service replacement behavior.

## 7. Serverless auto-pause and failures

SQLAlchemy uses **NullPool** and **pyodbc pooling is disabled before any connection**.
Closing a request/session releases the physical connection. Socket.IO handshakes
also release their read transaction; live sockets do not hold idle DB sessions.
Every new physical connection applies the required filtered-index SET options,
a 5-second lock timeout and a 30-second query timeout. No background database
heartbeat or readiness poll is added.

Connection-opening retries handle Azure transient/resume errors (including 40613)
and login timeouts. Requests get at most **3 attempts**, 5-second login timeout each,
with 1- and 2-second backoff (roughly 18 seconds plus driver/network overhead).
Startup migrations get **20 attempts**, backoff capped at 5 seconds (87 seconds of backoff, roughly three
minutes including login timeouts). Authentication and certificate failures are not
retried. Statements and transactions are **never replayed**; a dropped connection
may leave a write's outcome uncertain, so refresh current state before retrying an
action. Exhausted HTTP database requests return a generic 503 with Retry-After: 5;
raw ODBC errors, SQL parameters and credentials are not logged or returned.

The first connection to a paused Azure SQL database can fail while waking it; resume
can take about a minute. An initial user request may receive 503 before resume
completes, then succeed on refresh. Keep auto-pause disabled if that latency is
unacceptable. NullPool adds login/TLS overhead to active requests; evaluate observed
latency and concurrency before changing pooling. Open classroom views periodically
refresh state and will keep SQL active. Close those tabs, query tools and other DB
clients to allow auto-pause. Portal/query monitoring that opens sessions can also
wake/prevent pause. Features such as geo-replication, long-term backup retention
and logical-server DNS aliases can prevent auto-pause; check eligibility before
enabling them. Storage is billed while compute is paused; minimum compute is
billed while active. Auto-pause is conditional, not a promise of zero idle cost.
See [Azure SQL auto-pause/resume](https://learn.microsoft.com/en-us/azure/azure-sql/database/serverless-tier-auto-pause-resume)
and [SQLAlchemy/pyodbc pooling](https://docs.sqlalchemy.org/en/21/dialects/mssql.html#pyodbc-pooling-connection-close-behavior).

Operator commands expose fixed categories only:

| Category | Action |
| --- | --- |
| `dns-resolution` | Verify canonical SQL hostname and App Service DNS resolution. |
| `network-timeout` / `database-connection` | Check firewall, outbound route/ports, driver and serverless status. Do not keep restarting against an unreachable endpoint. |
| `tls-verification` | Keep Encrypt=yes/TrustServerCertificate=no; check runtime CA roots and canonical host. |
| `database-authentication` | Check the contained user, password encoding and selected database. |
| `database-privileges` | Verify CONNECT/CREATE TABLE and CONTROL on dbo for the same application user. |
| `migration-timeout` | Investigate blocking/long DDL; do not bypass locking or disable timeout protection. |
| `alembic-migration` | Check the reviewed release chain and current version in protected SQL tooling. |

`check-db` is an explicit read-only diagnostic and **does wake SQL**. Never print
`DATABASE_URL`, `SECRET_KEY`, passwords, bound SQL values or raw driver exceptions.
Gunicorn access logs are disabled because URLs can contain public session identifiers;
keep platform HTTP logging/Application Insights URL, body, cookie and exception
capture off or appropriately redacted, with restricted access and retention. Startup
logs contain revision identifiers and fixed failure categories only.
