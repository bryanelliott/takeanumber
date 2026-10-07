provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  resource_providers_to_register  = ["Microsoft.Web", "Microsoft.Sql"]

  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
