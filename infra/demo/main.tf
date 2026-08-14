locals {
  common_tags = merge(var.tags, {
    application = "lzug"
    environment = "demo"
    managed-by  = "opentofu"
    persistence = "ephemeral"
  })
}

resource "azurerm_resource_group" "demo" {
  name     = "${var.name_prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "demo" {
  name                = "${var.name_prefix}-logs"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5
  tags                = local.common_tags
}

resource "azurerm_container_app_environment" "demo" {
  name                       = "${var.name_prefix}-env"
  location                   = azurerm_resource_group.demo.location
  resource_group_name        = azurerm_resource_group.demo.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.demo.id
  public_network_access      = "Enabled"
  tags                       = local.common_tags
}

resource "azurerm_container_app" "demo" {
  name                         = "${var.name_prefix}-app"
  container_app_environment_id = azurerm_container_app_environment.demo.id
  resource_group_name          = azurerm_resource_group.demo.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.common_tags

  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = var.container_port
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1

    http_scale_rule {
      name                = "http-requests"
      concurrent_requests = 20
    }

    init_container {
      name   = "lzug-demo-seed"
      image  = var.demo_artifact_pair.seed_image
      cpu    = 0.25
      memory = "0.5Gi"

      volume_mounts {
        name = "demo-data"
        path = "/data"
      }
    }

    container {
      name   = "lzug-demo-app"
      image  = var.demo_artifact_pair.app_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "LZUG_DATA_DIR"
        value = "/data"
      }

      dynamic "env" {
        for_each = var.container_environment
        content {
          name  = env.key
          value = env.value
        }
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = var.container_port
        path                    = "/api/health"
        initial_delay           = 5
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 6
        success_count_threshold = 1
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = var.container_port
        path                    = "/api/health"
        initial_delay           = 30
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }

      volume_mounts {
        name = "demo-data"
        path = "/data"
      }
    }

    volume {
      name         = "demo-data"
      storage_type = "EmptyDir"
    }
  }
}

resource "azurerm_consumption_budget_resource_group" "demo" {
  name              = "${var.name_prefix}-monthly"
  resource_group_id = azurerm_resource_group.demo.id
  amount            = var.budget_amount_eur
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
    end_date   = var.budget_end_date
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = var.budget_contact_emails
  }
}

resource "github_repository_environment" "demo" {
  repository          = var.github_repository
  environment         = "demo"
  can_admins_bypass   = false
  prevent_self_review = true

  deployment_branch_policy {
    protected_branches     = true
    custom_branch_policies = false
  }
}
