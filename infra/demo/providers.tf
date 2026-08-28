provider "azurerm" {
  subscription_id = var.azure_subscription_id

  features {}
}

provider "github" {
  owner = var.github_owner
}
