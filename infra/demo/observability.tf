locals {
  uptime_targets = var.external_monitoring_enabled ? {
    landingpage = var.landingpage_url
    warmup      = "${var.demo_url}/api/ready"
  } : {}
}

resource "azurerm_monitor_action_group" "demo" {
  name                = "${var.name_prefix}-operations"
  resource_group_name = azurerm_resource_group.demo.name
  short_name          = "lzug-demo"
  tags                = local.common_tags

  dynamic "email_receiver" {
    for_each = toset(var.budget_contact_emails)
    content {
      name                    = "maintainer-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_application_insights" "demo" {
  count = var.external_monitoring_enabled ? 1 : 0

  name                                 = "${var.name_prefix}-uptime"
  location                             = azurerm_resource_group.demo.location
  resource_group_name                  = azurerm_resource_group.demo.name
  workspace_id                         = azurerm_log_analytics_workspace.demo.id
  application_type                     = "web"
  daily_data_cap_in_gb                 = var.application_insights_daily_cap_gb
  daily_data_cap_notifications_enabled = true
  internet_ingestion_enabled           = true
  internet_query_enabled               = false
  local_authentication_enabled         = false
  tags                                 = local.common_tags
}

resource "azurerm_application_insights_standard_web_test" "demo" {
  for_each = local.uptime_targets

  name                    = "${var.name_prefix}-${each.key}"
  location                = azurerm_resource_group.demo.location
  resource_group_name     = azurerm_resource_group.demo.name
  application_insights_id = azurerm_application_insights.demo[0].id
  geo_locations           = var.uptime_geo_locations
  frequency               = var.uptime_frequency_seconds
  timeout                 = 120
  retry_enabled           = true
  enabled                 = true
  tags                    = local.common_tags

  request {
    url                              = each.value
    http_verb                        = "GET"
    follow_redirects_enabled         = true
    parse_dependent_requests_enabled = false
  }

  validation_rules {
    expected_status_code        = 200
    ssl_check_enabled           = true
    ssl_cert_remaining_lifetime = 14
  }
}

resource "azurerm_monitor_metric_alert" "uptime" {
  for_each = azurerm_application_insights_standard_web_test.demo

  name                = "${var.name_prefix}-${each.key}-unavailable"
  resource_group_name = azurerm_resource_group.demo.name
  scopes              = [azurerm_application_insights.demo[0].id, each.value.id]
  description         = "The public demo ${each.key} availability test failed from one location."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT5M"
  auto_mitigate       = true
  enabled             = true
  tags                = local.common_tags

  application_insights_web_test_location_availability_criteria {
    web_test_id           = each.value.id
    component_id          = azurerm_application_insights.demo[0].id
    failed_location_count = 1
  }

  action {
    action_group_id = azurerm_monitor_action_group.demo.id
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert" "application_errors" {
  name                    = "${var.name_prefix}-application-errors"
  location                = azurerm_resource_group.demo.location
  resource_group_name     = azurerm_resource_group.demo.name
  data_source_id          = azurerm_log_analytics_workspace.demo.id
  description             = "Frontend or backend errors emitted by the public demo."
  enabled                 = true
  auto_mitigation_enabled = true
  severity                = 2
  frequency               = 5
  time_window             = 5
  query_type              = "ResultCount"
  # ResultCount evaluates rows, so the zero aggregate must not remain a row.
  query = <<-QUERY
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == "${azurerm_container_app.demo.name}"
    | extend event_payload = parse_json(Log_s)
    | where tostring(event_payload.event) in ("backend_error", "frontend_error")
    | summarize AggregatedValue = count()
    | where AggregatedValue > 0
  QUERY
  tags  = local.common_tags

  trigger {
    operator  = "GreaterThan"
    threshold = 0
  }

  action {
    action_group = [azurerm_monitor_action_group.demo.id]
  }
}
