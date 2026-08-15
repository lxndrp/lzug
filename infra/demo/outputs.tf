output "demo_url" {
  description = "Public HTTPS URL of the scale-to-zero demo."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}"
}

output "health_endpoint" {
  description = "Public health endpoint used by the deployment smoke test in issue #126."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/health"
}

output "readiness_endpoint" {
  description = "Public readiness endpoint used after liveness and during demo warm-up."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/ready"
}

output "demo_status_endpoint" {
  description = "Public demo status endpoint used to verify initialization and the last reset."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/demo/status"
}

output "deployment" {
  description = "Non-sensitive identifiers required by the controlled deployment workflow."
  value = {
    azure_resource_group  = azurerm_resource_group.demo.name
    container_app         = azurerm_container_app.demo.name
    container_environment = azurerm_container_app_environment.demo.name
    github_environment    = github_repository_environment.demo.environment
    artifact_pair         = var.demo_artifact_pair
    latest_revision_name  = azurerm_container_app.demo.latest_revision_name
    revision_mode         = azurerm_container_app.demo.revision_mode
    reset_workflow        = azurerm_logic_app_workflow.demo_reset.name
    reset_timezone        = local.reset_timezone_iana
    deployment_digest     = split("@", var.demo_artifact_pair.app_image)[1]
    log_workspace         = azurerm_log_analytics_workspace.demo.name
    log_retention_days    = azurerm_log_analytics_workspace.demo.retention_in_days
    log_daily_quota_gb    = azurerm_log_analytics_workspace.demo.daily_quota_gb
    action_group          = azurerm_monitor_action_group.demo.name
    external_monitoring   = var.external_monitoring_enabled
  }
}
