locals {
  prefix       = "${var.app_name}-${var.environment}"
  web_app_name = coalesce(var.app_service_name, local.prefix)
  trusted_hosts = distinct(concat(
    ["${local.web_app_name}.azurewebsites.net"], var.trusted_hosts
  ))
  tags = merge(var.tags, {
    application = var.app_name
    environment = var.environment
    managed_by  = "terraform"
  })

  sql_serverless = can(regex("^(GP|HS)_S_", var.sql_database_sku_name))
  sql_username   = coalesce(var.sql_app_username, var.sql_admin_username)
  sql_password   = var.sql_app_password != null ? var.sql_app_password : var.sql_admin_password

  # urlencode is form/query encoding: convert its space '+' to '%20' for URL
  # userinfo. Literal plus signs already become %2B and must remain encoded.
  sql_encoded_username = replace(urlencode(local.sql_username), "+", "%20")
  sql_encoded_password = replace(urlencode(local.sql_password), "+", "%20")
  database_url = join("", [
    "mssql+pyodbc://${local.sql_encoded_username}:${local.sql_encoded_password}",
    "@${azurerm_mssql_server.main.fully_qualified_domain_name}:1433/${var.sql_database_name}",
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
  ])
}
