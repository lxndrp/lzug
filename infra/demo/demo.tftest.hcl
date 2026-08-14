mock_provider "azurerm" {
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg"
    }
  }

  mock_resource "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.OperationalInsights/workspaces/lzug-demo-logs"
    }
  }

  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.App/managedEnvironments/lzug-demo-env"
    }
  }

  mock_resource "azurerm_container_app" {
    defaults = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.App/containerApps/lzug-demo-app"
      latest_revision_name = "lzug-demo-app--mock"
    }
  }
}
mock_provider "github" {}

run "demo_contract" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    image_reference       = "ghcr.io/lxndrp/demo-artifact@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2036-09-01T00:00:00Z"
  }

  assert {
    condition     = azurerm_resource_group.demo.location == "westeurope"
    error_message = "The default demo region must remain in Western Europe."
  }

  assert {
    condition     = azurerm_container_app.demo.template[0].min_replicas == 0 && azurerm_container_app.demo.template[0].max_replicas == 1
    error_message = "The demo must scale from zero to at most one replica."
  }

  assert {
    condition     = azurerm_container_app.demo.template[0].container[0].cpu == 0.5 && azurerm_container_app.demo.template[0].container[0].memory == "1Gi"
    error_message = "The demo container must retain explicit low resource limits."
  }

  assert {
    condition     = azurerm_container_app.demo.template[0].container[0].image == var.image_reference
    error_message = "The planned container must use the selected immutable digest."
  }

  assert {
    condition     = length(azurerm_container_app.demo.template[0].volume) == 0 && length(azurerm_container_app.demo.template[0].container[0].volume_mounts) == 0
    error_message = "The public demo must not declare persistent or mounted volumes."
  }

  assert {
    condition     = azurerm_container_app.demo.ingress[0].external_enabled && !azurerm_container_app.demo.ingress[0].allow_insecure_connections && azurerm_container_app.demo.ingress[0].target_port == 8000
    error_message = "Only managed HTTPS ingress to the application port may be public."
  }

  assert {
    condition     = azurerm_container_app_environment.demo.public_network_access == "Enabled" && length(azurerm_container_app.demo.template[0].container[0].env) == 0
    error_message = "The environment must expose only the declared app ingress and must not invent runtime settings for issue #124."
  }

  assert {
    condition     = azurerm_consumption_budget_resource_group.demo.amount == 25
    error_message = "The configured monthly budget must be part of every plan."
  }

  assert {
    condition     = github_repository_environment.demo.environment == "demo" && !github_repository_environment.demo.can_admins_bypass
    error_message = "The protected GitHub demo environment must be managed declaratively."
  }
}
