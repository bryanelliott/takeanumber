# Offline plans only: all Azure APIs are mocked. These are deliberately fake secrets.
mock_provider "azurerm" {
  override_during = plan
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/takeanumber-test-rg"
    }
  }
  mock_resource "azurerm_service_plan" {
    defaults = {
      id = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/takeanumber-test-rg/providers/Microsoft.Web/serverFarms/takeanumber-prod-plan"
    }
  }
  mock_resource "azurerm_mssql_server" {
    defaults = {
      id                          = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/takeanumber-test-rg/providers/Microsoft.Sql/servers/takeanumber-test-sql"
      fully_qualified_domain_name = "takeanumber-test-sql.database.windows.net"
    }
  }
  mock_resource "azurerm_linux_web_app" {
    defaults = {
      default_hostname                  = "takeanumber-prod.azurewebsites.net"
      outbound_ip_address_list          = ["192.0.2.1"]
      possible_outbound_ip_address_list = ["192.0.2.1", "192.0.2.2"]
    }
  }
  mock_resource "azurerm_mssql_database" {
    defaults = {
      # These provider-computed values are used only when config omits an option.
      min_capacity                = 0
      auto_pause_delay_in_minutes = -1
    }
  }
}

variables {
  subscription_id     = "11111111-1111-1111-1111-111111111111"
  resource_group_name = "takeanumber-test-rg"
  sql_server_name     = "takeanumber-test-sql"
  sql_admin_password  = "T3st only+@:/?&%-not-a-real-secret"
  secret_key          = "test-only-signing-key-not-a-production-secret"
}

run "secure_serverless_defaults_and_password_encoding" {
  command = plan

  assert {
    condition = (
      azurerm_service_plan.main.worker_count == 1 &&
      azurerm_service_plan.main.os_type == "Linux" &&
      azurerm_linux_web_app.main.https_only &&
      azurerm_linux_web_app.main.site_config[0].websockets_enabled &&
      azurerm_linux_web_app.main.site_config[0].app_command_line == "bash startup.sh" &&
      azurerm_linux_web_app.main.site_config[0].application_stack[0].python_version == "3.13"
    )
    error_message = "The application must use HTTPS, one Linux worker, Python 3.13, WebSockets and the migration startup wrapper."
  }
  assert {
    condition = (
      azurerm_mssql_database.main.min_capacity == 0.5 &&
      azurerm_mssql_database.main.auto_pause_delay_in_minutes == 60 &&
      length(azurerm_mssql_firewall_rule.allowed) == 0 &&
      length(azurerm_mssql_firewall_rule.azure_services) == 0
    )
    error_message = "Serverless defaults must not silently open a broad SQL firewall."
  }
  assert {
    condition     = azurerm_linux_web_app.main.app_settings["DATABASE_URL"] == "mssql+pyodbc://takeanumber_admin:T3st%20only%2B%40%3A%2F%3F%26%25-not-a-real-secret@takeanumber-test-sql.database.windows.net:1433/takeanumber?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
    error_message = "Encode URL userinfo correctly, particularly space versus literal plus; require verified TLS."
  }
  assert {
    condition     = !contains(keys(azurerm_linux_web_app.main.app_settings), "MIGRATION_DATABASE_URL")
    error_message = "Runtime and migrations must share a single DATABASE_URL."
  }
}

run "provisioned_sku_omits_serverless_arguments" {
  command = plan
  variables {
    sql_database_sku_name = "S0"
  }
  assert {
    condition     = azurerm_mssql_database.main.min_capacity == 0 && azurerm_mssql_database.main.auto_pause_delay_in_minutes == -1
    error_message = "Do not send serverless-only fields for provisioned databases."
  }
}

run "contained_user_and_narrow_firewall" {
  command = plan
  variables {
    sql_app_username = "user name+@:/?&"
    sql_app_password = "T3st only+@:/?&%-not-a-real-secret"
    sql_firewall_rules = {
      app_service_01 = { start_ip_address = "192.0.2.1", end_ip_address = "192.0.2.1" }
    }
  }
  assert {
    condition     = startswith(azurerm_linux_web_app.main.app_settings["DATABASE_URL"], "mssql+pyodbc://user%20name%2B%40%3A%2F%3F%26:")
    error_message = "The contained username needs correct URL userinfo encoding too."
  }
  assert {
    condition     = length(azurerm_mssql_firewall_rule.allowed) == 1 && length(azurerm_mssql_firewall_rule.azure_services) == 0
    error_message = "Individual App Service IPs should not enable the broad Azure rule."
  }
}

run "broad_azure_rule_requires_explicit_opt_in" {
  command = plan
  variables {
    sql_allow_azure_services = true
  }
  assert {
    condition     = azurerm_mssql_firewall_rule.azure_services[0].start_ip_address == "0.0.0.0" && azurerm_mssql_firewall_rule.azure_services[0].end_ip_address == "0.0.0.0"
    error_message = "Use Azure's special rule, never an all-Internet address range."
  }
}

run "disabled_public_access_creates_no_public_rules" {
  command = plan
  variables {
    sql_public_network_access_enabled = false
    sql_allow_azure_services          = true
    sql_firewall_rules = {
      app_service_01 = { start_ip_address = "192.0.2.1", end_ip_address = "192.0.2.1" }
    }
  }
  assert {
    condition     = length(azurerm_mssql_firewall_rule.allowed) == 0 && length(azurerm_mssql_firewall_rule.azure_services) == 0
    error_message = "Public SQL firewall rules must be omitted when SQL public access is disabled."
  }
}

run "reject_unpaired_contained_credentials" {
  command = plan
  variables {
    sql_app_username = "takeanumber_app"
  }
  expect_failures = [azurerm_linux_web_app.main]
}

run "reject_min_capacity_above_sku_maximum" {
  command = plan
  variables {
    sql_min_capacity = 2
  }
  expect_failures = [azurerm_mssql_database.main]
}

run "reject_all_internet_firewall" {
  command = plan
  variables {
    sql_firewall_rules = {
      unsafe = { start_ip_address = "0.0.0.0", end_ip_address = "255.255.255.255" }
    }
  }
  expect_failures = [var.sql_firewall_rules]
}

run "reject_reversed_firewall_range" {
  command = plan
  variables {
    sql_firewall_rules = {
      reversed = { start_ip_address = "192.0.2.20", end_ip_address = "192.0.2.10" }
    }
  }
  expect_failures = [var.sql_firewall_rules]
}

