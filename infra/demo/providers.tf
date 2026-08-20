locals {
  application_insights_generated_rule_disabled = true
}

provider "azurerm" {
  subscription_id = var.azure_subscription_id

  features {
    application_insights {
      disable_generated_rule = local.application_insights_generated_rule_disabled
    }
  }
}

provider "github" {
  owner = var.github_owner
}
