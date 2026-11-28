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
  # Standard SKU on purpose (cost). The checks below need the Premium SKU (~10x price) and,
  # for private access, a private endpoint + network module that does not exist yet.
  # Revisit for prod when the networking increment lands.
  # checkov:skip=CKV_AZURE_167: retention policy is Premium-only
  # checkov:skip=CKV_AZURE_233: zone redundancy is Premium-only
  # checkov:skip=CKV_AZURE_165: geo-replication is Premium-only; single-region deployment
  # checkov:skip=CKV_AZURE_139: CI pushes over the public endpoint until a private endpoint exists
  # checkov:skip=CKV_AZURE_237: dedicated data endpoints are Premium-only
  # checkov:skip=CKV_AZURE_164: trust policy / content trust is Premium-only
  # checkov:skip=CKV_AZURE_166: quarantine policy is Premium-only; Trivy scans images in CI
  name               = replace("${var.name_prefix}acr", "-", "")
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
