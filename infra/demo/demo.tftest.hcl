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

  mock_resource "azurerm_monitor_action_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.Insights/actionGroups/lzug-demo-operations"
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

  mock_resource "azurerm_logic_app_workflow" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.Logic/workflows/lzug-demo-reset"
      identity = {
        principal_id = "11111111-1111-1111-1111-111111111111"
        tenant_id    = "22222222-2222-2222-2222-222222222222"
      }
    }
  }

  mock_resource "azurerm_role_definition" {
    defaults = {
      role_definition_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/lzug-demo-rg/providers/Microsoft.Authorization/roleDefinitions/33333333-3333-3333-3333-333333333333"
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
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00Z"
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
    condition = (
      azurerm_container_app.demo.template[0].container[0].cpu == 0.5 &&
      azurerm_container_app.demo.template[0].container[0].memory == "1Gi" &&
      azurerm_container_app.demo.template[0].init_container[0].cpu == 0.25 &&
      azurerm_container_app.demo.template[0].init_container[0].memory == "0.5Gi"
    )
    error_message = "The app and seed initializer must retain explicit low resource limits."
  }

  assert {
    condition = (
      azurerm_container_app.demo.template[0].container[0].image == var.demo_artifact_pair.app_image &&
      azurerm_container_app.demo.template[0].init_container[0].image == var.demo_artifact_pair.seed_image
    )
    error_message = "The planned app and seed initializer must use the selected immutable digest pair."
  }

  assert {
    condition = (
      length(azurerm_container_app.demo.template[0].volume) == 1 &&
      azurerm_container_app.demo.template[0].volume[0].name == "demo-data" &&
      azurerm_container_app.demo.template[0].volume[0].storage_type == "EmptyDir" &&
      azurerm_container_app.demo.template[0].container[0].volume_mounts[0].name == "demo-data" &&
      azurerm_container_app.demo.template[0].container[0].volume_mounts[0].path == "/data" &&
      azurerm_container_app.demo.template[0].init_container[0].volume_mounts[0].name == "demo-data" &&
      azurerm_container_app.demo.template[0].init_container[0].volume_mounts[0].path == "/data"
    )
    error_message = "The app and initializer must share exactly one replica-scoped EmptyDir mounted only at /data."
  }

  assert {
    condition     = azurerm_container_app.demo.ingress[0].external_enabled && !azurerm_container_app.demo.ingress[0].allow_insecure_connections && azurerm_container_app.demo.ingress[0].target_port == 8000
    error_message = "Only managed HTTPS ingress to the application port may be public."
  }

  assert {
    condition = (
      azurerm_container_app_environment.demo.public_network_access == "Enabled" &&
      length(azurerm_container_app_environment.demo.workload_profile) == 1 &&
      alltrue([
        for profile in azurerm_container_app_environment.demo.workload_profile :
        profile.name == "Consumption" &&
        profile.workload_profile_type == "Consumption" &&
        profile.minimum_count == 0 &&
        profile.maximum_count == 0
      ]) &&
      length(azurerm_container_app.demo.template[0].container[0].env) == 3 &&
      azurerm_container_app.demo.template[0].container[0].env[0].name == "LZUG_DATA_DIR" &&
      azurerm_container_app.demo.template[0].container[0].env[0].value == "/data" &&
      azurerm_container_app.demo.template[0].container[0].env[1].name == "LZUG_DEPLOYMENT_DIGEST" &&
      azurerm_container_app.demo.template[0].container[0].env[1].value == "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" &&
      azurerm_container_app.demo.template[0].container[0].env[2].name == "LZUG_CORS_ALLOWED_ORIGINS" &&
      azurerm_container_app.demo.template[0].container[0].env[2].value == "https://lzug.repertoire.papaspyrou.name"
    )
    error_message = "The app must retain the shared /data path, immutable deployment digest, and exact landing-page CORS origin by default."
  }

  assert {
    condition = (
      azurerm_container_app.demo.template[0].container[0].liveness_probe[0].path == "/api/health" &&
      azurerm_container_app.demo.template[0].container[0].readiness_probe[0].path == "/api/ready"
    )
    error_message = "Liveness and application readiness must remain separate signals."
  }

  assert {
    condition = (
      azurerm_consumption_budget_resource_group.demo.amount == 25 &&
      alltrue([
        for notification in azurerm_consumption_budget_resource_group.demo.notification :
        toset(notification.contact_groups) == toset([azurerm_monitor_action_group.demo.id])
      ])
    )
    error_message = "The configured monthly budget and testable action group must be part of every plan."
  }

  assert {
    condition = (
      !strcontains(file("${path.module}/observability.tf"), "azurerm_application_insights") &&
      !strcontains(file("${path.module}/observability.tf"), "azurerm_monitor_metric_alert") &&
      !strcontains(file("${path.module}/variables.tf"), "external_monitoring") &&
      !strcontains(file("${path.module}/providers.tf"), "application_insights")
    )
    error_message = "The demo must not create Application Insights, web tests, Smart Detection, or static metric-alert resources."
  }

  assert {
    condition = (
      azurerm_log_analytics_workspace.demo.retention_in_days == 30 &&
      azurerm_log_analytics_workspace.demo.daily_quota_gb == 0.5 &&
      strcontains(azurerm_monitor_scheduled_query_rules_alert.application_errors.query, "frontend_error") &&
      strcontains(azurerm_monitor_scheduled_query_rules_alert.application_errors.query, "backend_error") &&
      strcontains(azurerm_monitor_scheduled_query_rules_alert.application_errors.query, "| summarize AggregatedValue = count()") &&
      strcontains(azurerm_monitor_scheduled_query_rules_alert.application_errors.query, "| where AggregatedValue > 0") &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.query_type == "ResultCount" &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.trigger[0].operator == "GreaterThan" &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.trigger[0].threshold == 0 &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.frequency == 60 &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.time_window == 60 &&
      azurerm_monitor_scheduled_query_rules_alert.application_errors.auto_mitigation_enabled &&
      length(azurerm_monitor_scheduled_query_rules_alert.application_errors.action) == 1 &&
      toset(azurerm_monitor_scheduled_query_rules_alert.application_errors.action[0].action_group) == toset([azurerm_monitor_action_group.demo.id]) &&
      length(azurerm_monitor_action_group.demo.email_receiver) == 1 &&
      alltrue([
        for receiver in azurerm_monitor_action_group.demo.email_receiver :
        receiver.use_common_alert_schema
      ])
    )
    error_message = "Application error detection must return no result for zero events, one result for errors, and resolve statefully."
  }

  assert {
    condition = (
      github_repository_environment.demo.environment == "demo" &&
      !github_repository_environment.demo.can_admins_bypass &&
      !github_repository_environment.demo.deployment_branch_policy[0].protected_branches &&
      github_repository_environment.demo.deployment_branch_policy[0].custom_branch_policies &&
      github_repository_environment_deployment_policy.demo["master"].branch_pattern == "master" &&
      github_repository_environment_deployment_policy.demo["snapshot"].tag_pattern == "demo/v*-SNAPSHOT.*" &&
      github_repository_environment_deployment_policy.demo["release"].tag_pattern == "v*"
    )
    error_message = "The GitHub demo environment must declaratively preserve its selected master, snapshot, and stable release policies."
  }

  assert {
    condition = (
      azurerm_logic_app_workflow.demo_reset.identity[0].type == "SystemAssigned" &&
      azurerm_logic_app_trigger_recurrence.daily_reset.frequency == "Day" &&
      azurerm_logic_app_trigger_recurrence.daily_reset.interval == 1 &&
      azurerm_logic_app_trigger_recurrence.daily_reset.time_zone == "W. Europe Standard Time" &&
      azurerm_logic_app_trigger_recurrence.daily_reset.schedule[0].at_these_hours == toset([3]) &&
      azurerm_logic_app_trigger_recurrence.daily_reset.schedule[0].at_these_minutes == toset([0])
    )
    error_message = "The system-identity reset workflow must run daily at 03:00 Europe/Berlin with DST handling."
  }

  assert {
    condition = (
      toset(azurerm_role_definition.demo_reset.permissions[0].actions) == toset([
        "Microsoft.App/containerApps/read",
        "Microsoft.App/containerApps/start/action",
        "Microsoft.App/containerApps/stop/action",
      ]) &&
      azurerm_role_assignment.demo_reset.scope == azurerm_container_app.demo.id &&
      azurerm_role_assignment.demo_reset.principal_id == azurerm_logic_app_workflow.demo_reset.identity[0].principal_id
    )
    error_message = "The Logic App identity may only read, stop, and start this one Container App."
  }

  assert {
    condition = (
      jsondecode(azurerm_logic_app_action_custom.stop_demo.body).inputs.authentication.type == "ManagedServiceIdentity" &&
      strcontains(jsondecode(azurerm_logic_app_action_custom.stop_demo.body).inputs.uri, "/stop?api-version=") &&
      strcontains(jsondecode(azurerm_logic_app_action_custom.start_demo.body).inputs.uri, "/start?api-version=") &&
      jsondecode(azurerm_logic_app_action_custom.check_health.body).inputs.uri == output.health_endpoint &&
      jsondecode(azurerm_logic_app_action_custom.check_readiness.body).inputs.uri == output.readiness_endpoint &&
      jsondecode(azurerm_logic_app_action_custom.check_demo_status.body).inputs.uri == output.demo_status_endpoint &&
      strcontains(azurerm_logic_app_action_custom.validate_demo_status.body, var.demo_artifact_pair.runtime_contract) &&
      strcontains(azurerm_logic_app_action_custom.validate_demo_status.body, var.demo_artifact_pair.seed_revision) &&
      strcontains(azurerm_logic_app_action_custom.validate_demo_status.body, "last_reset_at")
    )
    error_message = "The reset workflow must stop/start through managed identity and verify liveness, readiness, expected seed, initialization, and last reset."
  }

  assert {
    condition     = output.deployment.artifact_pair == var.demo_artifact_pair && output.deployment.reset_timezone == "Europe/Berlin"
    error_message = "The handoff and rollback output must preserve the complete verified digest pair and Berlin reset contract."
  }
}

run "reject_moving_demo_tags" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app:latest"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed:demo"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00Z"
  }

  expect_failures = [var.demo_artifact_pair]
}

run "accept_bound_snapshot_artifact_pair" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "demo/v0.2.0-SNAPSHOT.0123456"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00Z"
  }

  assert {
    condition     = output.deployment.artifact_pair.runtime_contract == "lzug-demo-health-ready-v1"
    error_message = "A green snapshot pair must retain the versioned health/readiness manifest contract."
  }
}

run "reject_legacy_runtime_contract" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.2"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "legacy-health-only"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00Z"
  }

  expect_failures = [var.demo_artifact_pair]
}

run "reject_partial_environment_policy_adoption" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    github_environment_deployment_policy_ids = {
      master = "123456"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00Z"
  }

  expect_failures = [var.github_environment_deployment_policy_ids]
}

run "reject_invalid_budget_end_calendar_date" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-02-31T00:00:00Z"
  }

  expect_failures = [var.budget_end_date]
}

run "reject_invalid_budget_end_timestamp" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2028-07-31T00:00:00"
  }

  expect_failures = [var.budget_end_date]
}

run "reject_budget_end_not_later" {
  command = plan

  plan_options {
    refresh = false
  }

  variables {
    azure_subscription_id = "00000000-0000-0000-0000-000000000000"
    location              = "westeurope"
    demo_artifact_pair = {
      app_image          = "ghcr.io/lxndrp/lzug-demo-app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      seed_image         = "ghcr.io/lxndrp/lzug-demo-seed@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
      product_tag        = "v0.1.1"
      product_commit     = "0123456789abcdef0123456789abcdef01234567"
      runtime_contract   = "lzug-demo-health-ready-v1"
      schema_fingerprint = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
      seed_revision      = "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01"
    }
    budget_amount_eur     = 25
    budget_contact_emails = ["demo-operations@example.invalid"]
    budget_start_date     = "2026-09-01T00:00:00Z"
    budget_end_date       = "2026-08-31T00:00:00Z"
  }

  expect_failures = [var.budget_end_date]
}
