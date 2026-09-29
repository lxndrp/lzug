locals {
  container_app_api_version = "2025-07-01"
  reset_timezone_iana       = "Europe/Berlin"
  reset_timezone_azure      = "W. Europe Standard Time"
  management_audience       = "https://management.azure.com/"
  container_app_api_uri     = "https://management.azure.com${azurerm_container_app.demo.id}?api-version=${local.container_app_api_version}"
}

resource "azurerm_logic_app_workflow" "demo_reset" {
  name                = "${var.name_prefix}-reset"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  enabled             = true
  tags                = local.common_tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_logic_app_trigger_recurrence" "daily_reset" {
  name         = "daily-reset-europe-berlin"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  frequency    = "Day"
  interval     = 1
  time_zone    = local.reset_timezone_azure

  schedule {
    at_these_hours   = [3]
    at_these_minutes = [0]
  }
}

resource "azurerm_logic_app_action_custom" "stop_demo" {
  name         = "Stop_demo"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "Http"
    inputs = {
      method = "POST"
      uri    = "https://management.azure.com${azurerm_container_app.demo.id}/stop?api-version=${local.container_app_api_version}"
      authentication = {
        type     = "ManagedServiceIdentity"
        audience = local.management_audience
      }
    }
    runAfter = {}
  })
}

resource "azurerm_logic_app_action_custom" "wait_for_stopped" {
  name         = "Wait_for_stopped"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type       = "Until"
    expression = "@equals(body('Read_stop_status')?['properties']?['runningStatus'], 'Stopped')"
    limit = {
      count   = 30
      timeout = "PT10M"
    }
    actions = {
      Read_stop_status = {
        type = "Http"
        inputs = {
          method = "GET"
          uri    = local.container_app_api_uri
          authentication = {
            type     = "ManagedServiceIdentity"
            audience = local.management_audience
          }
        }
        runAfter = {}
      }
      Delay_stop_poll = {
        type = "Wait"
        inputs = {
          interval = {
            count = 10
            unit  = "Second"
          }
        }
        runAfter = {
          Read_stop_status = ["Succeeded"]
        }
      }
    }
    runAfter = {
      Stop_demo = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.stop_demo]
}

resource "azurerm_logic_app_action_custom" "start_demo" {
  name         = "Start_demo"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "Http"
    inputs = {
      method = "POST"
      uri    = "https://management.azure.com${azurerm_container_app.demo.id}/start?api-version=${local.container_app_api_version}"
      authentication = {
        type     = "ManagedServiceIdentity"
        audience = local.management_audience
      }
    }
    runAfter = {
      Wait_for_stopped = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.wait_for_stopped]
}

resource "azurerm_logic_app_action_custom" "wait_for_running" {
  name         = "Wait_for_running"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type       = "Until"
    expression = "@equals(body('Read_start_status')?['properties']?['runningStatus'], 'Running')"
    limit = {
      count   = 30
      timeout = "PT10M"
    }
    actions = {
      Read_start_status = {
        type = "Http"
        inputs = {
          method = "GET"
          uri    = local.container_app_api_uri
          authentication = {
            type     = "ManagedServiceIdentity"
            audience = local.management_audience
          }
        }
        runAfter = {}
      }
      Delay_start_poll = {
        type = "Wait"
        inputs = {
          interval = {
            count = 10
            unit  = "Second"
          }
        }
        runAfter = {
          Read_start_status = ["Succeeded"]
        }
      }
    }
    runAfter = {
      Start_demo = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.start_demo]
}

resource "azurerm_logic_app_action_custom" "check_health" {
  name         = "Check_health"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "Http"
    inputs = {
      method = "GET"
      uri    = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/health"
      retryPolicy = {
        type     = "fixed"
        count    = 30
        interval = "PT10S"
      }
    }
    runAfter = {
      Wait_for_running = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.wait_for_running]
}

resource "azurerm_logic_app_action_custom" "check_demo_status" {
  name         = "Check_demo_status"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "Http"
    inputs = {
      method = "GET"
      uri    = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/demo/status"
    }
    runAfter = {
      Check_readiness = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.check_readiness]
}

resource "azurerm_logic_app_action_custom" "check_readiness" {
  name         = "Check_readiness"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "Http"
    inputs = {
      method = "GET"
      uri    = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/ready"
      retryPolicy = {
        type     = "fixed"
        count    = 30
        interval = "PT10S"
      }
    }
    runAfter = {
      Check_health = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.check_health]
}

resource "azurerm_logic_app_action_custom" "validate_demo_status" {
  name         = "Validate_demo_status"
  logic_app_id = azurerm_logic_app_workflow.demo_reset.id
  body = jsonencode({
    type = "If"
    expression = {
      and = [
        { equals = ["@body('Check_demo_status')?['initialized']", true] },
        { equals = ["@body('Check_demo_status')?['initialization_status']", "ready"] },
        { equals = ["@body('Check_demo_status')?['runtime_contract']", var.demo_artifact_pair.runtime_contract] },
        { equals = ["@body('Check_demo_status')?['seed_revision']", var.demo_artifact_pair.seed_revision] },
        { equals = ["@body('Check_demo_status')?['reset_timezone']", local.reset_timezone_iana] },
        { greater = ["@ticks(body('Check_demo_status')?['last_reset_at'])", "@ticks(addMinutes(utcNow(), -15))"] },
      ]
    }
    actions = {}
    else = {
      actions = {
        Fail_reset = {
          type = "Terminate"
          inputs = {
            runStatus = "Failed"
            runError = {
              code    = "DemoStatusInvalid"
              message = "The demo did not report the expected initialized seed and recent reset."
            }
          }
          runAfter = {}
        }
      }
    }
    runAfter = {
      Check_demo_status = ["Succeeded"]
    }
  })

  depends_on = [azurerm_logic_app_action_custom.check_demo_status]
}

resource "azurerm_role_definition" "demo_reset" {
  name        = "${var.name_prefix}-stop-start"
  scope       = azurerm_resource_group.demo.id
  description = "Read, stop, and start only the lzug public demo Container App."

  permissions {
    actions = [
      "Microsoft.App/containerApps/read",
      "Microsoft.App/containerApps/start/action",
      "Microsoft.App/containerApps/stop/action",
    ]
    not_actions = []
  }

  assignable_scopes = [azurerm_resource_group.demo.id]
}

resource "azurerm_role_assignment" "demo_reset" {
  scope              = azurerm_container_app.demo.id
  role_definition_id = azurerm_role_definition.demo_reset.role_definition_resource_id
  principal_id       = azurerm_logic_app_workflow.demo_reset.identity[0].principal_id
  principal_type     = "ServicePrincipal"
}
