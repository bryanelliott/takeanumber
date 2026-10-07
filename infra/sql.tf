resource "azurerm_mssql_server" "main" {
  name                          = var.sql_server_name
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "12.0"
  administrator_login           = var.sql_admin_username
  administrator_login_password  = var.sql_admin_password
  minimum_tls_version           = "1.2"
  connection_policy             = "Proxy"
  public_network_access_enabled = var.sql_public_network_access_enabled
  tags                          = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_mssql_database" "main" {
  name                        = var.sql_database_name
  server_id                   = azurerm_mssql_server.main.id
  sku_name                    = var.sql_database_sku_name
  collation                   = var.sql_collation
  max_size_gb                 = var.sql_max_size_gb
  min_capacity                = local.sql_serverless ? var.sql_min_capacity : null
  auto_pause_delay_in_minutes = local.sql_serverless ? var.sql_auto_pause_minutes : null
  zone_redundant              = var.sql_zone_redundant
  storage_account_type        = var.sql_backup_storage_redundancy
  tags                        = local.tags

  lifecycle {
    # Terraform lifecycle flags must be literals, not variables. See README for
    # deliberate non-production teardown; do not remove this for routine changes.
    prevent_destroy = true
    precondition {
      condition     = !local.sql_serverless || var.sql_min_capacity <= try(tonumber(regex("[0-9]+$", var.sql_database_sku_name)), 0)
      error_message = "Serverless min_capacity cannot exceed the vCore maximum encoded in the selected SKU."
    }
  }
}

resource "azurerm_mssql_firewall_rule" "allowed" {
  for_each = var.sql_public_network_access_enabled ? var.sql_firewall_rules : {}

  name             = each.key
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = each.value.start_ip_address
  end_ip_address   = each.value.end_ip_address
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
  count = var.sql_public_network_access_enabled && var.sql_allow_azure_services ? 1 : 0

  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
