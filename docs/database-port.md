# Database port audit

## Scope and result

The PostgreSQL-specific chain is retired because no production data needs preserving.
`0001_sqlserver_baseline` is a new initial Alembic revision for an **empty Azure SQL
Database**, with all five currently implemented models. Future migrations extend
this revision. Existing databases are neither converted nor automatically dropped.

Production uses one SQL-authenticated application credential and one
`DATABASE_URL`. Startup invokes `deploy-upgrade` before Gunicorn; the Flask factory
never migrates. The publish-profile release workflow has no production DB secret,
network dependency, migration job or Azure login. The exact operations are in
[deployment.md](deployment.md).

The [Terraform infrastructure](../infra/README.md) can bootstrap with the SQL
administrator credential as explicitly allowed for initial simplicity. A contained
application user is the recommended narrower alternative; both runtime and migrations
switch together. This does not add a separate migration credential.

## PostgreSQL-specific behavior found and replacement

| Area audited | Finding / replacement |
| --- | --- |
| Driver/dialect | psycopg/libpq URLs replaced by mssql+pyodbc / Microsoft ODBC Driver 18. |
| UUID | Already used generic SQLAlchemy Uuid and Python uuid4; now native UNIQUEIDENTIFIER. No integer-ID substitution. |
| Timestamps/defaults | TIMESTAMPTZ and now()/clock_timestamp() replaced by DATETIMEOFFSET and SYSDATETIMEOFFSET(); Python stays timezone-aware. |
| Booleans | IS TRUE became BIT-compatible equality. Boolean defaults compile to 1/0. |
| Unicode/collation | Names use NVARCHAR(200) plus a 100-code-point CHECK; binary collations preserve token/code/hash/status case sensitivity. Exact status checks also reject padded trailing spaces. |
| Regex checks | PostgreSQL regular expressions replaced by SQL Server LIKE patterns, explicit Unicode whitespace sets, LEN and DATALENGTH checks. |
| Partial unique indexes | mssql_where filtered unique indexes preserve one active session, one active identity entry and one serving entry. Nullable token hashes use IS NOT NULL filtering because SQL Server ordinary unique indexes permit only one NULL. |
| Foreign keys | RESTRICT replaced by NO ACTION; history remains protected. Preference deletion cascade remains. |
| Upsert/RETURNING | PostgreSQL ON CONFLICT and explicit RETURNING replaced by ORM locked select/insert/update transactions; SQLAlchemy handles generated values through the SQL Server dialect. No MERGE is introduced. |
| Queue locks | FOR UPDATE/SHARE replaced by UPDLOCK,HOLDLOCK and HOLDLOCK hints. Range locks protect missing-key inserts; snapshots remain consistent. Tests cover simultaneous starts/joins/updates and rollback. |
| Aggregates | FILTER replaced by conditional COUNT(CASE); EXTRACT(epoch FROM interval) replaced by DATEDIFF_BIG(microsecond) with decimal arithmetic. Fractional-duration rounding tests remain. |
| Migration locks/timeouts | PostgreSQL advisory lock and SET LOCAL statements replaced by transaction-owned sp_getapplock, SET LOCK_TIMEOUT, XACT_ABORT and ODBC query timeout. Alembic uses the same physical transaction and final-head check. |
| Errors | psycopg SQLSTATE/diag constraint inspection replaced by pyodbc SQLSTATE/native SQL Server codes. Raw messages/parameters are never emitted by operator commands or request error handlers. |
| Pooling/resume | Disable pyodbc pooling before connecting, SQLAlchemy NullPool, bounded connection-opening-only retries. No transaction replay or health DB query. |
| Other features | No application ARRAY/JSONB/JSON columns, ILIKE queries, PostgreSQL sequences, stored procedures, triggers, custom enums or database-generated UUID extensions needed porting. |
| Test infrastructure | Replace PostgreSQL services with SQL Server 2022 Linux, ODBC 18 and a dedicated test DB/user. Keep all application/security suites required. Remove only obsolete migration-mode tests and engine-specific historical upgrade-chain tests; replace them with baseline/future-revision tests. |

## Validation and limits

Use the exact CI commands in README. Tests check initialization, real DDL rollback,
competing migration locks, final-head verification, duplicate constraints, fractional
wait calculations, queue races, minimum application grants, closed idle connections,
bounded resume retries, startup failure barriers and database-free liveness.
The full suite still collects optional browser tests; the normal CI gate excludes
only that marker. SQL Server 2022 is the isolated compatibility test target;
no tests ever connect to production Azure SQL.

Production provisioning, driver availability in the chosen App Service image,
App Service outbound firewall access, actual Azure certificate chain and real
serverless wake latency still need the first-deployment checks in the runbook.
A local SQL container cannot certify those Azure infrastructure properties.
One shared application credential necessarily has schema-mutation rights at runtime;
keep this database dedicated to the application and protect that credential.
The application-side login and statement timeout budgets are finite, but driver/DNS
scheduling adds overhead; the App Service startup deadline is the outer limit.

## Changed files

| File | Change |
| --- | --- |
| `.dockerignore` | Exclude local credentials, caches and virtual environments from Docker build context. |
| `.env.example` | Local SQL Server URLs and explicit local-only certificate bypass. |
| `.github/workflows/ci.yml` | Required Python 3.13/ODBC 18/SQL Server container-based CI; optional browser marker retained. |
| `.github/workflows/deploy.yml` | Publish-profile deployment after CI; remove runner migrations and migration-mode inputs. |
| `AGENTS.md` | Align contributor database/startup/test rules with the authorized architecture. |
| `README.md` | SQL Server local provisioning/testing and new production release instructions. |
| `app/__init__.py` | Install engine lifecycle hooks and safe database-error HTTP responses; factory never migrates. |
| `app/auth/services.py` | Inspect SQL Server unique-constraint violations for duplicate registration. |
| `app/cli.py` | Transaction-owned sp_getapplock migration wrapper, bounded timeouts, head validation and resume budget. |
| `app/config.py` | Validate mssql+pyodbc URLs, Driver 18, verified production TLS and isolated tests; select NullPool. |
| `app/database.py` | Disable driver pooling; configure session settings, bounded opening retries, SQL clock and native error helpers. |
| `app/models/help_session.py` | Filtered active-session index, case-sensitive code/status, checks and NO ACTION foreign key. |
| `app/models/instructor.py` | Unicode name length/whitespace and email checks, case-sensitive password hash, SQL clock. |
| `app/models/instructor_setting.py` | SQL Server clock/defaults; preserve Boolean/range/unique ownership constraints. |
| `app/models/queue_entry.py` | Filtered active/serving indexes, Unicode name validation, state/time checks and NO ACTION foreign keys. |
| `app/models/student_identity.py` | Filtered non-null hash uniqueness, case-sensitive hash validation and SQL clocks. |
| `app/realtime.py` | Reject failed database handshakes without logging raw driver messages. |
| `app/services/deployment.py` | SQL Server credential-safe DNS/network/TLS/auth/privilege/migration diagnostics. |
| `app/services/queue.py` | SQL Server snapshot lock hints, wall clock and portable conditional count. |
| `app/services/sessions.py` | SQL Server mutation lock hints, BIT predicate and native duplicate-code handling. |
| `app/services/settings.py` | Atomic locked select/insert/update instead of PostgreSQL upsert. |
| `app/services/student_identity.py` | Atomic identity select/insert/update instead of PostgreSQL upsert/RETURNING. |
| `app/services/wait_time.py` | DATEDIFF_BIG microsecond duration and decimal averages. |
| `compose.yaml` | Separate SQL Server development/test servers and a shared-loopback Linux test runner. |
| `docs/architecture.md` | SQL Server transactions, pooling, startup migration and CI architecture. |
| `docs/data-model.md` | Native UUID/timestamp/Unicode/filtered-index semantics and clean baseline. |
| `docs/database-port.md` | Dialect audit, limits and complete changed-file inventory (this document). |
| `docs/deployment.md` | Exact Portal settings, contained-user SQL, first/future deployments and serverless operations. |
| `docs/implementation-plan.md` | Revised foundation and Milestone 10 deployment acceptance criteria. |
| `docs/requirements.md` | Authorized Azure SQL single-credential/startup-migration deployment requirements. |
| `migrations/env.py` | Preserve application logging while loading Alembic logging configuration. |
| `migrations/versions/0001_instructor_create_instructor.py` | Removed retired PostgreSQL revision; its contents remain in Git history. |
| `migrations/versions/0001_sqlserver_baseline.py` | Frozen initial SQL Server DDL for the five current models; no runtime metadata/create_all. |
| `migrations/versions/0002_help_session_create_help_session.py` | Removed retired PostgreSQL revision; its contents remain in Git history. |
| `migrations/versions/0003_student_queue_create_student_identity_and_queue_entry.py` | Removed retired PostgreSQL revision; its contents remain in Git history. |
| `migrations/versions/0004_queue_advancement_one_serving_per_session.py` | Removed retired PostgreSQL revision; its contents remain in Git history. |
| `migrations/versions/0005_instructor_settings.py` | Removed retired PostgreSQL revision; its contents remain in Git history. |
| `requirements.txt` | Replace psycopg packages with pinned pyodbc. |
| `scripts/check_migration_inputs.py` | Removed obsolete manual/runner migration-input validator. |
| `scripts/init_test_database.py` | Guarded disposable test DB/login setup with the documented non-owner schema permissions. |
| `startup.sh` | Validate settings/driver, run deploy-upgrade, then exec one worker; failed migrations block Gunicorn. |
| `tests/Dockerfile` | Reproducible Linux Python 3.13 image with native Driver 18 and CA roots. |
| `tests/conftest.py` | Check actual SQL Server database/user before Alembic and per-test data cleanup. |
| `tests/test_advancement.py` | Keep serving uniqueness assertions using native SQL Server errors and clock. |
| `tests/test_config.py` | Driver/TLS/query-option validation and isolated SQL Server test selection. |
| `tests/test_connection_lifecycle.py` | Physical close/NullPool, bounded resume retry, no statement replay, health and safe 503 checks. |
| `tests/test_database.py` | Real SQL Server connection/database/user and check-db verification. |
| `tests/test_deploy_migrations.py` | Application lock, timeouts, idempotence, revision validation and transactional DDL rollback. |
| `tests/test_deployment_diagnostics.py` | SQL Server error categories and secret redaction. |
| `tests/test_migration_inputs.py` | Removed tests for obsolete manual/runner migration modes. |
| `tests/test_migrations.py` | Initial baseline round trip/model match, idempotent preservation and a real subsequent revision. |
| `tests/test_production.py` | Azure SQL URL, production TLS and existing host/cookie/proxy safety. |
| `tests/test_queue.py` | Retain all queue constraints/concurrency checks with SQL Server clock/error assertions. |
| `tests/test_sessions.py` | Retain session mutation/ownership/lock tests with SQL Server hints/errors. |
| `tests/test_settings.py` | Use SQL Server wall time in preference persistence tests. |
| `tests/test_sqlserver_schema.py` | Unicode limits, whitespace, case sensitivity, null-hash uniqueness and non-owner user rights. |
| `tests/test_startup.py` | Execute the real Bash startup barrier; enforce DB-free publish-profile workflow. |
| `tests/test_wait_time.py` | Use SQL Server wall time; retain duration/rounding/history coverage. |
