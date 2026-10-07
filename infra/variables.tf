variable "subscription_id" {
  type        = string
  description = "Azure subscription ID for infrastructure provisioning, not GitHub deployment authentication."
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "Supply an Azure subscription UUID."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Resource group managed by this configuration; import it first if it already exists."
  validation {
    condition     = can(regex("^[A-Za-z0-9_()-][A-Za-z0-9_.()-]{0,89}$", var.resource_group_name)) && !endswith(var.resource_group_name, ".")
    error_message = "Use a valid resource group name of 1-90 characters, without a trailing dot."
  }
}

variable "location" {
  type        = string
  description = "Azure region. Verify chosen SQL/App Service SKUs and quota are available here before apply."
  default     = "canadacentral"
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "app_name" {
  type        = string
  description = "Lowercase naming prefix; combine with environment or override globally unique service names."
  default     = "takeanumber"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,29}[a-z0-9]$", var.app_name))
    error_message = "Use 3-31 lowercase letters/digits/hyphens, beginning with a letter and ending alphanumerically."
  }
}

variable "environment" {
  type        = string
  description = "Naming/tag label, e.g. prod or dev. The hosted application always uses production security settings."
  default     = "prod"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,9}$", var.environment))
    error_message = "Use a lowercase environment label of 1-10 characters."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional Azure tags. Application, environment and managed_by are maintained by this configuration."
  default     = {}
}

variable "app_service_name" {
  type        = string
  description = "Optional globally unique Web App name. Defaults to app_name-environment."
  default     = null
  validation {
    condition     = var.app_service_name == null ? true : can(regex("^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$", var.app_service_name))
    error_message = "Use 2-60 lowercase letters/digits/hyphens with alphanumeric ends."
  }
}

variable "app_service_plan_sku" {
  type        = string
  description = "Dedicated Linux Basic/Standard/Premium plan SKU. Free/shared/elastic plans are intentionally unsupported."
  default     = "B1"
  validation {
    condition     = can(regex("^(B[123]|S[123]|P[0-5]m?v[234])$", var.app_service_plan_sku))
    error_message = "Select a dedicated B, S or P v2/v3/v4 SKU; verify regional availability."
  }
}

variable "python_version" {
  type        = string
  description = "Built-in Linux Python runtime. Application dependencies are tested with 3.13; verify before changing."
  default     = "3.13"
  validation {
    condition     = contains(["3.13", "3.14"], var.python_version)
    error_message = "Use Python 3.13 or 3.14 supported by this provider; 3.13 is the tested default."
  }
}

variable "always_on" {
  type        = bool
  description = "Keep the dedicated web process warm. This does not keep SQL awake via /health."
  default     = true
}

variable "health_check_path" {
  type        = string
  description = "Liveness endpoint. TakeANumber currently provides /health; changing this requires matching app support."
  default     = "/health"
  validation {
    condition     = can(regex("^/[A-Za-z0-9/_-]+$", var.health_check_path))
    error_message = "Use an absolute URL path without a query string or hostname."
  }
}

variable "trusted_hosts" {
  type        = list(string)
  description = "Additional exact trusted hostnames. The named azurewebsites.net hostname is always included; custom DNS/TLS binding is separate."
  default     = []
  validation {
    condition     = alltrue([for host in var.trusted_hosts : can(regex("^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$", host))])
    error_message = "Use exact hostnames only, with no schemes, paths, ports or wildcards."
  }
}

variable "secret_key" {
  type        = string
  sensitive   = true
  description = "Stable random Flask signing secret, at least 32 characters. Supply securely; stored in Terraform state."
  validation {
    condition     = length(var.secret_key) >= 32 && !startswith(var.secret_key, "replace-with-")
    error_message = "Generate a stable random SECRET_KEY of at least 32 characters."
  }
}

variable "sql_server_name" {
  type        = string
  description = "Globally unique Azure SQL logical server name, without .database.windows.net."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", var.sql_server_name))
    error_message = "Use 2-63 lowercase letters/digits/hyphens, with alphanumeric ends."
  }
}

variable "sql_database_name" {
  type        = string
  description = "Dedicated application database. Restricted to simple URL-safe names to avoid database-path decoding ambiguity."
  default     = "takeanumber"
  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_-]{0,127}$", var.sql_database_name)) && !contains(["master", "model", "msdb", "tempdb"], lower(var.sql_database_name))
    error_message = "Use an application database name of 1-128 letters/digits/underscore/hyphen, not a system database."
  }
}

variable "sql_admin_username" {
  type        = string
  description = "SQL authentication administrator. Also used by the app initially unless a contained application user is supplied."
  default     = "takeanumber_admin"
  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_-]{0,127}$", var.sql_admin_username)) && !contains(["sa", "admin", "administrator", "root", "guest"], lower(var.sql_admin_username))
    error_message = "Use a non-reserved SQL administrator name, beginning with a letter."
  }
}

variable "sql_admin_password" {
  type        = string
  sensitive   = true
  description = "Strong SQL administrator password, 16-128 characters, compliant with Azure policy; stored in Terraform state."
  validation {
    condition     = length(var.sql_admin_password) >= 16 && length(var.sql_admin_password) <= 128
    error_message = "Supply a generated password of 16-128 characters meeting Azure SQL complexity requirements."
  }
}

variable "sql_app_username" {
  type        = string
  description = "Optional existing contained application user, shared by requests and migrations. Supply its password too; Terraform does not create SQL users."
  default     = null
  validation {
    condition     = var.sql_app_username == null ? true : length(trimspace(var.sql_app_username)) > 0 && length(var.sql_app_username) <= 128
    error_message = "A contained application username must be nonempty and at most 128 characters."
  }
}

variable "sql_app_password" {
  type        = string
  sensitive   = true
  description = "Optional contained application's password. One credential is used for both runtime and migrations; stored in state."
  default     = null
  validation {
    condition     = var.sql_app_password == null ? true : length(var.sql_app_password) >= 16 && length(var.sql_app_password) <= 128
    error_message = "Supply a generated application password of 16-128 characters."
  }
}

variable "sql_database_sku_name" {
  type        = string
  description = "Azure SQL Database SKU; GP_S_Gen5_1 is the serverless default. Check regional availability/quota and pricing."
  default     = "GP_S_Gen5_1"
  validation {
    condition     = can(regex("^(GP_|BC_|HS_)[A-Za-z0-9_]+$|^(Basic|S[0-9]+|P[0-9]+)$", var.sql_database_sku_name))
    error_message = "Choose a standalone Azure SQL Database SKU (DTU or GP/BC/HS); pools/warehouses require a different design."
  }
}

variable "sql_min_capacity" {
  type        = number
  description = "Serverless minimum vCores while active; omitted entirely for provisioned SKUs."
  default     = 0.5
  validation {
    condition     = var.sql_min_capacity >= 0.5 && floor(var.sql_min_capacity * 2) == var.sql_min_capacity * 2
    error_message = "Use a positive half-vCore increment of at least 0.5; it must fit the selected serverless SKU."
  }
}

variable "sql_auto_pause_minutes" {
  type        = number
  description = "Serverless auto-pause delay, 15-10080 minutes or -1 to disable. Omitted for provisioned SKUs; tier-specific eligibility still applies."
  default     = 60
  validation {
    condition     = var.sql_auto_pause_minutes == -1 || (var.sql_auto_pause_minutes >= 15 && var.sql_auto_pause_minutes <= 10080 && floor(var.sql_auto_pause_minutes) == var.sql_auto_pause_minutes)
    error_message = "Use -1 or an integer delay between 15 and 10080 minutes."
  }
}

variable "sql_max_size_gb" {
  type        = number
  description = "Database size cap in GB; must be supported by the selected SKU."
  default     = 32
  validation {
    condition     = var.sql_max_size_gb > 0 && floor(var.sql_max_size_gb) == var.sql_max_size_gb
    error_message = "Use a positive whole number of GB supported by the SQL SKU."
  }
}

variable "sql_zone_redundant" {
  type        = bool
  description = "Enable only after confirming zone redundancy is supported by this SQL tier, SKU and region."
  default     = false
}

variable "sql_collation" {
  type        = string
  description = "Optional database collation override; changing it replaces the database and is blocked by destroy protection."
  default     = "SQL_Latin1_General_CP1_CI_AS"
  nullable    = true
}

variable "sql_backup_storage_redundancy" {
  type        = string
  description = "SQL backup storage redundancy, separate from compute zone redundancy; evaluate cost and recovery requirements."
  default     = "Geo"
  validation {
    condition     = contains(["Local", "Zone", "Geo", "GeoZone"], var.sql_backup_storage_redundancy)
    error_message = "Use Local, Zone, Geo or GeoZone, supported in the selected region."
  }
}

variable "sql_public_network_access_enabled" {
  type        = bool
  description = "Enable firewall-controlled public SQL access. False isolates SQL; this configuration creates no alternate private path."
  default     = true
}

variable "sql_allow_azure_services" {
  type        = bool
  description = "Explicit broad Azure 0.0.0.0 special firewall rule. False by default; use individual App Service outbound IP rules instead."
  default     = false
}

variable "sql_firewall_rules" {
  type = map(object({
    start_ip_address = string
    end_ip_address   = string
  }))
  description = "Named IPv4 SQL firewall ranges. After first apply add App Service outbound IPs as individual start=end rules, then apply again before code deployment."
  default     = {}
  validation {
    condition = alltrue([for name, rule in var.sql_firewall_rules :
      can(regex("^[A-Za-z0-9_-]{1,128}$", name)) &&
      can(cidrnetmask("${rule.start_ip_address}/32")) &&
      can(cidrnetmask("${rule.end_ip_address}/32")) &&
      rule.start_ip_address != "0.0.0.0" && rule.end_ip_address != "255.255.255.255"
    ])
    error_message = "Use named IPv4 ranges; all-Internet ranges and the Azure special rule belong neither here nor in ordinary allowlists."
  }
  validation {
    condition = alltrue([for rule in values(var.sql_firewall_rules) : try(
      sum([for i, octet in split(".", rule.start_ip_address) : tonumber(octet) * pow(256, 3 - i)]) <=
      sum([for i, octet in split(".", rule.end_ip_address) : tonumber(octet) * pow(256, 3 - i)]), false
    )])
    error_message = "Each SQL firewall range must begin at or before its ending IPv4 address."
  }
}
