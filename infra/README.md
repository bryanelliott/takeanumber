# TakeANumber Azure infrastructure

This root configuration provisions Azure resources only. GitHub Actions deploys
the application ZIP with a publish profile. App Service startup runs the application's
`deploy-upgrade` wrapper using the same `DATABASE_URL` as runtime, then starts
Gunicorn only after Alembic succeeds. Terraform never connects to SQL, creates
application tables, or runs migrations.

## Default architecture and ownership

- A resource group in `canadacentral` (configurable).
- A dedicated Linux B1 App Service plan with **exactly one instance**, no autoscale,
  and a Python 3.13 web app with Always On, WebSockets, HTTPS and TLS 1.2 minimum.
- `bash startup.sh`, `/health`, and all required production application settings.
- An Azure SQL logical server with SQL authentication, verified encrypted app
  connections, TLS 1.2 minimum and Proxy connection policy (TCP 1433).
- An empty Azure SQL Database, default `GP_S_Gen5_1`, 0.5 minimum vCores, 60-minute
  auto-pause, 32 GB size cap, no compute zone redundancy, geo-redundant backup storage.
- Public SQL networking with **no client firewall rules initially**. Before code
  deployment, add the app's actual outbound IPs and apply again, as below.
- Literal `prevent_destroy = true` on both SQL server and database.

There are no private endpoints, VNets, private DNS zones, VMs, slots, Redis,
PostgreSQL resources, managed identities, service principals, OIDC configuration,
GitHub resources, SQL provisioners or `null_resource` hooks. Linux and one instance
are deliberate constants, matching the application's single-worker Socket.IO design.
Changing `environment` changes names/tags, not hosted application security settings.

Terraform manages resource configuration, firewall rules and application settings.
GitHub manages application code releases. `startup.sh`/Alembic manages schema state.
Keep these boundaries: do not add ZIP deployment to Terraform or migrations to a
Terraform provisioner. See [the application runbook](../docs/deployment.md).

## Prerequisites and inputs

Use Terraform **1.11 or newer, below 2.0** and the checked-in provider lock file.
This configuration is validated with AzureRM **5.8.0**, constrained to its patch
series. AzureRM is the only provider. Upgrade it deliberately and review the plan.

For provisioning, an operator must authenticate to Azure and have permission to
create the resource group/resources and register `Microsoft.Web`/`Microsoft.Sql`.
The examples use interactive Azure CLI `az login`; this is **only for Terraform
infrastructure administration**. GitHub releases and application migrations never
need that login or a deployment identity. No identity resources are created here.
Subscription Contributor is sufficient; use narrower pre-provisioned scopes where
your organization requires them and arrange provider registration separately.

Confirm in Azure Portal that your subscription/region supports the selected App
Service and SQL SKUs, quotas, serverless tier and optional redundancy. Defaults are
examples, not a promise of regional capacity. Names for SQL servers and web apps
must be globally unique. If managing existing resources, import their correct IDs
before planning; do not apply a new configuration over an existing deployment blindly.

Required user-supplied variables:

| Variable | Purpose |
| --- | --- |
| `subscription_id` | AzureRM target subscription, nonsecret |
| `resource_group_name` | New resource group name, or one imported into this state |
| `sql_server_name` | Globally unique logical SQL server name |
| `sql_admin_password` | Strong generated SQL administrator password, sensitive |
| `secret_key` | Stable random Flask signing key of at least 32 characters, sensitive |

Review the defaults in `variables.tf`, especially service names, location, SKUs,
backup redundancy and firewall settings. `app_service_name` overrides the derived
`app_name-environment` name. `trusted_hosts` adds exact public hostnames; this does
not provision custom DNS or TLS bindings. The standard named Azure hostname is
included automatically, and a postcondition checks the actual returned hostname.
If Azure assigns a different hostname, obtain it from Portal Overview, add it to
`trusted_hosts`, and apply before code deployment. This prevents a self-reference
cycle between the Web App's computed hostname and its own app settings.

## Credentials and the one-user database model

Initially, **both runtime and startup migrations use the configured SQL administrator
credential** through one `DATABASE_URL`. This makes the first empty-database deployment
work without external SQL provisioning. The administrator is powerful across its SQL
logical server; use a server dedicated to this application and protect its credential.
A contained application user scoped to the one database is preferable before sustained
production use. Optional instructions below switch both phases together to that user.

Supply `sql_admin_password` and `secret_key` through protected `TF_VAR_*` environment
variables or a secret manager. Keep values stable between runs. Do not regenerate
the signing key on every plan: rotation invalidates existing sessions. Do not put
secrets into committed tfvars, CLI `-var` arguments, command history or debug logs.

Terraform builds the URL with `replace(urlencode(value), "+", "%20")` for username
and password. Form encoding uses `+` for spaces; URL userinfo must instead use `%20`.
Literal `+` becomes `%2B`, while `@ : / ? & %` are also percent-encoded. Do **not**
pre-encode the supplied password. Database names are limited to simple URL-safe
characters because SQLAlchemy's database-path handling differs from userinfo.
The fixed query is:

```text
?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
```

There is no second migration URL. No secret or full URL is output. `sensitive` hides
normal CLI display; it does **not encrypt Terraform state or saved plans**. State
contains SQL passwords, the signing key, application settings and potentially
provider-returned publishing credentials. See the state section before first apply.

## First deployment (PowerShell)

1. Authenticate for infrastructure administration, initialize, and create the
   ignored local variables file. Run from the repository root:

   ```powershell
   az login
   az account set --subscription '<your-subscription-id>'
   Set-Location infra
   terraform init
   if (!(Test-Path terraform.tfvars)) { Copy-Item terraform.tfvars.example terraform.tfvars }
   notepad terraform.tfvars
   ```

   Replace the subscription/name placeholders and review all regional/SKU choices.
   Never overwrite an existing tfvars file containing your established settings.
   Use an Azure account with the permissions above, not a GitHub deployment principal.

2. Supply stable secrets from your password manager using masked prompts. These
   commands do not echo the values or put them into shell command history:

   ```powershell
   $env:TF_VAR_sql_admin_password = [Net.NetworkCredential]::new('', (Read-Host 'SQL administrator password' -AsSecureString)).Password
   $env:TF_VAR_secret_key = [Net.NetworkCredential]::new('', (Read-Host 'Stable Flask SECRET_KEY' -AsSecureString)).Password
   ```

   Store both secrets securely for future runs. Azure requires a strong SQL password;
   use 16-128 generated characters. For Flask use at least 32 cryptographically random
   characters, such as a securely generated 32-byte value represented as hex.

3. Validate, review the plan and apply. The saved plan contains secrets: keep it in
   an access-controlled, unsynced directory or protected workspace, never in Git.

   ```powershell
   terraform fmt -check -recursive
   terraform validate
   terraform plan -out=first.tfplan
   terraform apply first.tfplan
   terraform output
   ```

   No application code is installed yet, so the startup command and `/health` may
   fail until the GitHub deployment. That is expected during resource provisioning.

4. **Authorize App Service in the SQL firewall before deploying code.** Run:

   ```powershell
   terraform output -json app_service_outbound_ip_addresses
   ```

   Copy every returned address into `sql_firewall_rules` in `terraform.tfvars`,
   with a stable descriptive name and start=end for each address. For example,
   replacing these documentation-only IPs with the real outputs:

   ```hcl
   sql_firewall_rules = {
     app_service_01 = { start_ip_address = "192.0.2.10", end_ip_address = "192.0.2.10" }
     app_service_02 = { start_ip_address = "192.0.2.11", end_ip_address = "192.0.2.11" }
   }
   ```

   ```powershell
   terraform plan -out=firewall.tfplan
   terraform apply firewall.tfplan
   ```

   The output includes current and possible outbound addresses to accommodate the
   current plan's worker placement. These are Azure shared infrastructure IPs, not
   a cryptographic identity for this app; SQL authentication is still required.
   Recheck them after plan/SKU changes. SQL firewall changes can take a few minutes
   to propagate. Add your administrator's public IP temporarily only if using the
   optional contained-user SQL below, then remove its rule through Terraform.

   This second **ordinary** apply is intentional: Terraform `for_each` keys must
   be known at plan time, while a new web app's outbound IPs are not. No targeted
   apply, shell provisioning or fragile computed-key workaround is needed.

   **Simpler, broader alternative:** set `sql_allow_azure_services = true` before
   the first apply. The explicit `0.0.0.0` to `0.0.0.0` Azure special rule permits
   network access from other Azure customers/resources too, not just this App
   Service. It is not the all-Internet range, and credentials remain required,
   but it is broader than the default allowlist. Never use
   `0.0.0.0` to `255.255.255.255`. Disabling public SQL access provides no private
   replacement path here and makes this web app unable to reach SQL.

5. In Portal, verify App Service Configuration shows Python 3.13, WebSockets,
   `bash startup.sh`, HTTPS Only and `/health`. Verify Microsoft ODBC Driver 18
   exists in the actual built-in Python runtime (`odbcinst -q -d` via Portal SSH).
   Terraform cannot install native packages inside Microsoft's built-in image.
   The app checks Driver 18 and fails closed if missing; resolve the runtime image
   prerequisite before release. Use the supported installation guidance in the
   [application runbook](../docs/deployment.md), never disable certificate verification.

6. Open App Service Overview and **Download publish profile**. Terraform enables
   SCM/WebDeploy basic publishing authentication and disables FTP publishing.
   Your Azure policies must permit SCM basic authentication for this release method.
   Store the XML directly in the GitHub **production environment secret**
   `AZURE_WEBAPP_PUBLISH_PROFILE`. Do not commit, output or leave the downloaded
   file in a shared directory. GitHub repository secrets also work if consistent
   with your environment policy; the existing workflow uses the production environment.

7. Set the GitHub production environment variables from these nonsecret outputs:

   ```powershell
   terraform output -raw app_service_name   # AZURE_WEBAPP_NAME
   terraform output -raw app_health_url    # APP_HEALTH_URL
   ```

   Protect the environment and main branch, require CI, and configure reviewers.
   Do not add SQL credentials to GitHub. Commit/push the reviewed application and
   Terraform source (including `.terraform.lock.hcl`), then run **Deploy Azure
   production** from main and approve the tested commit. GitHub installs no SQL
   connection to production; App Service startup performs migrations itself.

8. Inspect protected App Service startup logs for **Database upgraded to the release
   head** and a successful Gunicorn start. On the first release, Alembic revision
   `0001_sqlserver_baseline` creates the five application tables and version table.
   A failed migration blocks the new web process; do not bypass the wrapper.

   ```powershell
   $appHealthUrl = terraform output -raw app_health_url
   Invoke-RestMethod $appHealthUrl
   ```

   Expect `status: ok`. Health is liveness-only, so also verify database-backed
   behavior: open `<app_service_url>/auth/signup`, create the first instructor
   account, log in, start a session, join from another browser and advance/end it.
   Check settings and live updates. Never create application tables manually.

9. Check for a stable infrastructure plan:

   ```powershell
   terraform plan -detailed-exitcode
   # 0 = no changes; 2 = review a proposed change; 1 = error.
   Remove-Item Env:TF_VAR_sql_admin_password, Env:TF_VAR_secret_key
   ```

   Re-supply the same secrets on subsequent sessions. Terraform owns its settings:
   change tfvars/configuration rather than editing managed values only in Portal.
   GitHub should deploy code without rewriting stack/startup/app settings. Investigate
   unexpected drift instead of adding broad ignore_changes rules. No real Azure
   plan/apply or live drift check was performed during repository validation.

## Optional contained application user

AzureRM provisions SQL control-plane resources, not SQL users. This configuration
deliberately has no SQL execution provider, `local-exec`, `null_resource` or external
SQL dependency. For least privilege, after the empty database exists and your client
IP is temporarily authorized, connect directly to `takeanumber` as SQL administrator
with verified TLS using Portal Query editor or an authorized SQL client. Run once:

```sql
CREATE USER [takeanumber_app]
    WITH PASSWORD = '<generated-contained-user-password>', DEFAULT_SCHEMA = [dbo];
GRANT CONNECT, CREATE TABLE TO [takeanumber_app];
GRANT CONTROL ON SCHEMA::[dbo] TO [takeanumber_app];
```

Escape single quotes in the SQL password literal as `''`. These are user/grant
commands, not application schema initialization. In tfvars set
`sql_app_username = "takeanumber_app"`, then provide its password securely:

```powershell
$env:TF_VAR_sql_app_password = [Net.NetworkCredential]::new('', (Read-Host 'Contained application password' -AsSecureString)).Password
terraform plan -out=contained-user.tfplan
terraform apply contained-user.tfplan
```

Both runtime and startup migrations now use that same user and URL. Keep the SQL
administrator password supplied for managing the server resource; it is no longer
installed in App Service. Granting CONTROL on this dedicated application's dbo
schema supplies DML, table/index/constraint alteration and Alembic version access;
CREATE TABLE is required at database scope. `sp_getapplock` uses public membership
and needs no server administration grant. Future views/procedures may need their
specific CREATE permissions reviewed. See [the permission runbook](../docs/deployment.md).
Remove the temporary client firewall rule via Terraform after setup.

## State: local bootstrap and Azure Storage migration

No backend is hardcoded. `terraform init` initially uses local state. **Local state
is not an adequate shared production secret store.** Before production apply,
prefer an existing secured remote backend; alternatively bootstrap from an encrypted,
access-controlled, unsynced workstation directory and promptly migrate state.
Do not place real state/plans in a OneDrive/shared folder. Git ignore rules prevent
accidental commits, not cloud synchronization, backups or filesystem access.

To migrate later without creating a backend dependency cycle:

1. Separately provision an Azure Storage account and private blob container for
   state, outside this application's destroy scope. Enable HTTPS, encryption,
   blob versioning/soft delete, access controls and a firewall appropriate for
   operator access. Restrict storage keys; they grant broad account access.
2. Add `backend.tf` containing only:

   ```hcl
   terraform {
     backend "azurerm" {}
   }
   ```

3. Create an ignored, nonsecret `backend.hcl` (do not add a storage key):

   ```hcl
   resource_group_name  = "terraform-state-rg"
   storage_account_name = "<unique-existing-storage-account>"
   container_name       = "tfstate"
   key                  = "takeanumber/prod.tfstate"
   ```

4. Supply the existing storage account key from your secret manager via
   `ARM_ACCESS_KEY`, keeping it out of source, backend config and CLI arguments:

   ```powershell
   $env:ARM_ACCESS_KEY = [Net.NetworkCredential]::new('', (Read-Host 'State storage account key' -AsSecureString)).Password
   terraform init -migrate-state -backend-config=backend.hcl
   terraform plan
   Remove-Item Env:ARM_ACCESS_KEY
   ```

   Re-supply application/SQL variables for the plan as above. Confirm the expected
   resources and state blob before securely removing obsolete local state copies
   and plans. Keep protected recovery copies according to your retention policy.
   The blob backend provides state locking. Azure Storage authentication is for
   Terraform operators only and is independent of the GitHub publish profile.
   Use your organization's approved backend authentication method if it differs.

## Operations, costs and safe teardown

Serverless arguments are set only for GP_S/HS_S SKUs; provisioned SKUs omit them.
SQL tier, size, capacity and zone-redundancy combinations still depend on Azure
availability. General Purpose is the intended default; Hyperscale auto-pause has
additional eligibility/preview constraints. Check before changing tiers.

SQL auto-pause requires no sessions or user workload during its idle window.
TakeANumber disables pyodbc pooling and uses SQLAlchemy NullPool; `/health` never
connects to SQL. Open classroom tabs poll and will keep SQL active; query tools,
monitoring and some database features can also prevent pause or trigger resume.
Resume can take about a minute. Startup has longer bounded connection retries;
an initial HTTP request can return 503 and succeed after refresh. Statements and
transactions are never replayed. Disable auto-pause if that latency is unacceptable.
Storage/backup charges continue; active serverless compute has a minimum charge.
The App Service plan itself is continuously billed, independent of SQL auto-pause.

Always On defaults true on the supported paid dedicated plans. Free/shared plans
are excluded because their limitations do not match this deployment. Turning Always
On off introduces web-process cold starts and additional startup migrations. One
instance has no failover capacity; a health check does not create redundancy. Keep
one instance/one Gunicorn worker until the app's in-memory Socket.IO/rate-limit
architecture is explicitly redesigned. Public app/SCM access is retained for
students and GitHub-hosted publish-profile deployments; ingress restrictions and
custom-domain certificates require a separately reviewed change.

Protect the SQL database from accidental deletion or replacement: changes to names,
server IDs or collation may require replacement, so the lifecycle guard rejects
them. It does not block ordinary password, app setting or supported SKU updates.
Terraform requires lifecycle flags to be literal; there is no misleading variable
that pretends to toggle prevent_destroy. Both dev and prod start protected.
The guard only applies while the resource block remains in configuration and the
resource is managed by this state; it does not prevent out-of-band Portal deletion.

To deliberately destroy **non-production** infrastructure: verify subscription,
state and environment, preserve any needed data, then in a reviewed local change
set both `prevent_destroy` flags in `sql.tf` to false. Run
`terraform plan -destroy -out=destroy.tfplan`, inspect every deletion, then
`terraform apply destroy.tfplan`. Restore the guards before reusing the configuration.
Do not use `state rm` as a teardown shortcut. Production deletion requires an
explicit approved decommission/backup plan. Keep the state storage outside this
resource group so deleting the application cannot delete its recovery records.

## Validation and files

Repository validation does not need Azure credentials:

```powershell
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform test
```

The tests use mocked Azure APIs and plan-only runs. They verify URL encoding,
serverless/provisioned settings, one-worker HTTPS defaults, the single-URL credential
model and narrow/explicit-broad firewall options. They do not establish regional
SKU availability, provisioning permissions, native ODBC presence or real network
reachability; confirm those during the first deployment.

| File | Purpose |
| --- | --- |
| `versions.tf`, `.terraform.lock.hcl` | Terraform/provider constraints and provider checksums |
| `providers.tf` | Azure subscription, resource-provider registration and RG deletion guard |
| `variables.tf` | Described/validated inputs and sensitive secret variables |
| `locals.tf` | Names, tags, serverless detection and correctly encoded SQLAlchemy URL |
| `main.tf` | Resource group |
| `app_service.tf` | Single Linux plan/web app and production settings |
| `sql.tf` | Logical SQL server, protected database and controlled firewall rules |
| `outputs.tf` | Nonsecret deployment and inventory outputs |
| `terraform.tfvars.example` | Realistic configuration example without secrets |
| `tests/configuration.tftest.hcl` | Offline Terraform plan regression tests |
| `README.md` | This operator procedure |

Reference: [AzureRM Web App](https://registry.terraform.io/providers/hashicorp/azurerm/5.8.0/docs/resources/linux_web_app),
[SQL database](https://registry.terraform.io/providers/hashicorp/azurerm/5.8.0/docs/resources/mssql_database),
[Terraform URL encoding](https://developer.hashicorp.com/terraform/language/functions/urlencode),
[lifecycle protection](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle),
[Azure Storage backend](https://developer.hashicorp.com/terraform/language/backend/azurerm),
[Azure SQL auto-pause](https://learn.microsoft.com/en-us/azure/azure-sql/database/serverless-tier-auto-pause-resume).
