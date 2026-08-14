output "demo_url" {
  description = "Public HTTPS URL of the scale-to-zero demo."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}"
}

output "health_endpoint" {
  description = "Public health endpoint used by the deployment smoke test in issue #126."
  value       = "https://${azurerm_container_app.demo.ingress[0].fqdn}/api/health"
}

output "deployment" {
  description = "Non-sensitive identifiers required by the controlled deployment workflow."
  value = {
    azure_resource_group  = azurerm_resource_group.demo.name
    container_app         = azurerm_container_app.demo.name
    container_environment = azurerm_container_app_environment.demo.name
    github_environment    = github_repository_environment.demo.environment
    image_reference       = var.image_reference
    latest_revision_name  = azurerm_container_app.demo.latest_revision_name
    revision_mode         = azurerm_container_app.demo.revision_mode
  }
}
