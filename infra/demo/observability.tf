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

resource "azurerm_monitor_scheduled_query_rules_alert" "application_errors" {
  name                    = "${var.name_prefix}-application-errors"
  location                = azurerm_resource_group.demo.location
  resource_group_name     = azurerm_resource_group.demo.name
  data_source_id          = azurerm_log_analytics_workspace.demo.id
  description             = "Frontend or backend errors emitted by the public demo."
  enabled                 = true
  auto_mitigation_enabled = true
  severity                = 2
  frequency               = 60
  time_window             = 60
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
