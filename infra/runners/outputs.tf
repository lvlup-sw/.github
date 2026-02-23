################################################################################
# Outputs
################################################################################

output "runner_job_name" {
  description = "Name of the GitHub runner Container App Job"
  value       = azurerm_container_app_job.github_runner.name
}

output "runner_job_id" {
  description = "ID of the GitHub runner Container App Job"
  value       = azurerm_container_app_job.github_runner.id
}

output "acr_name" {
  description = "Name of the Container Registry"
  value       = azurerm_container_registry.runners.name
}

output "acr_login_server" {
  description = "Login server URL for the Container Registry"
  value       = azurerm_container_registry.runners.login_server
}

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.runners.name
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.runners.name
}

output "github_actions_client_id" {
  description = "AZURE_CLIENT_ID for GitHub Actions OIDC — set as a repo variable on lvlup-sw/.github"
  value       = azuread_application.github_actions.client_id
}

output "azure_tenant_id" {
  description = "AZURE_TENANT_ID for GitHub Actions OIDC — set as a repo variable on lvlup-sw/.github"
  value       = data.azurerm_client_config.current.tenant_id
}

output "azure_subscription_id" {
  description = "AZURE_SUBSCRIPTION_ID for GitHub Actions OIDC — set as a repo variable on lvlup-sw/.github"
  value       = data.azurerm_client_config.current.subscription_id
}
