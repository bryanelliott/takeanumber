output "resource_group_name" {
  description = "Managed Azure resource group."
  value       = azurerm_resource_group.main.name
}

output "app_service_name" {
  description = "GitHub production environment variable AZURE_WEBAPP_NAME."
  value       = azurerm_linux_web_app.main.name
}

output "app_service_default_hostname" {
  description = "Actual Azure default hostname; included in TRUSTED_HOSTS or checked by a postcondition."
  value       = azurerm_linux_web_app.main.default_hostname
}

output "app_service_url" {
  description = "Public application URL, available after GitHub deploys code and SQL access is configured."
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_health_url" {
  description = "GitHub production environment variable APP_HEALTH_URL; /health is liveness only."
  value       = "https://${azurerm_linux_web_app.main.default_hostname}${var.health_check_path}"
}

output "app_service_plan_name" {
  description = "Single-instance dedicated Linux App Service plan."
  value       = azurerm_service_plan.main.name
}

output "sql_server_fqdn" {
  description = "Canonical Azure SQL hostname; no credentials."
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "Application database created empty by Terraform. Alembic creates its schema at startup."
  value       = azurerm_mssql_database.main.name
}

output "app_service_outbound_ip_addresses" {
  description = "Current and possible outbound IPs. Use individual SQL firewall rules; recheck after plan/SKU changes."
  value = sort(distinct(concat(
    azurerm_linux_web_app.main.outbound_ip_address_list,
    azurerm_linux_web_app.main.possible_outbound_ip_address_list
  )))
}

output "resource_ids" {
  description = "Nonsecret IDs for inventory, import and operational tooling."
  value = {
    resource_group = azurerm_resource_group.main.id
    service_plan   = azurerm_service_plan.main.id
    web_app        = azurerm_linux_web_app.main.id
    sql_server     = azurerm_mssql_server.main.id
    sql_database   = azurerm_mssql_database.main.id
  }
}
