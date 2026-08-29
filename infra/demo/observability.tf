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
