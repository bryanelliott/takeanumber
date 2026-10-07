resource "azurerm_service_plan" "main" {
  name                = "${local.prefix}-plan"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.app_service_plan_sku
  worker_count        = 1
  tags                = local.tags
}

resource "azurerm_linux_web_app" "main" {
  name                = local.web_app_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_service_plan.main.location
  service_plan_id     = azurerm_service_plan.main.id

  https_only                                     = true
  public_network_access_enabled                  = true
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = true
  client_affinity_enabled                        = false
  tags                                           = local.tags

  site_config {
    application_stack {
      python_version = var.python_version
    }
    app_command_line                  = "bash startup.sh"
    always_on                         = var.always_on
    worker_count                      = 1
    websockets_enabled                = true
    minimum_tls_version               = "1.2"
    scm_minimum_tls_version           = "1.2"
    ftps_state                        = "Disabled"
    http2_enabled                     = true
    health_check_path                 = var.health_check_path
    health_check_eviction_time_in_min = 2
    # Public student access and GitHub-hosted publish-profile deployment.
    ip_restriction_default_action     = "Allow"
    scm_ip_restriction_default_action = "Allow"
    scm_use_main_ip_restriction       = false
  }

  app_settings = {
    APP_ENV                             = "production"
    SESSION_COOKIE_SECURE               = "true"
    FLASK_DEBUG                         = "0"
    FLASK_SKIP_DOTENV                   = "1"
    SCM_DO_BUILD_DURING_DEPLOYMENT      = "true"
    PROXY_FIX_X_FOR                     = "0"
    WEBSITES_CONTAINER_START_TIME_LIMIT = "600"
    SECRET_KEY                          = var.secret_key
    DATABASE_URL                        = local.database_url
    TRUSTED_HOSTS                       = join(",", local.trusted_hosts)
  }

  # Azure resources only: application ZIP deployment belongs to GitHub Actions.
  depends_on = [azurerm_mssql_database.main]

  lifecycle {
    precondition {
      condition     = (var.sql_app_username == null) == (var.sql_app_password == null)
      error_message = "Supply both contained application username/password, or neither to use the administrator initially."
    }
    postcondition {
      condition     = contains(local.trusted_hosts, self.default_hostname)
      error_message = "Azure assigned an unexpected default hostname. Add the actual default_hostname output to trusted_hosts and apply before deploying code."
    }
  }
}
