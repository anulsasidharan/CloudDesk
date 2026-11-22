# Azure scaffold: ACR + Container Apps + Key Vault + Log Analytics.
# Status: written, NOT applied, NOT validated against a real subscription. Needs cloud credentials.
terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.100" }
  }
  backend "azurerm" {} # configured with -backend-config=backend.hcl (git-ignored)
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "main" {
  name     = "${var.name_prefix}-rg"
  location = var.location
}

resource "azurerm_container_registry" "main" {
  name                = replace("${var.name_prefix}acr", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  admin_enabled       = false
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.name_prefix}-logs"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  retention_in_days   = var.environment == "prod" ? 90 : 30
}

# Container Apps environment, apps and Key Vault are the next increment (see docs).
