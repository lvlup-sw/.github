################################################################################
# GitHub Runners - Standalone Deployment
#
# Self-contained Terraform root for deploying GitHub Actions self-hosted
# runners without the full platform stack. All resources are defined inline
# to avoid coupling with the main infrastructure modules.
#
# Usage (azd):
#   cd infra/runners
#   azd init --environment runners-dev
#   azd env set TF_VAR_github_runner_pat "ghp_xxx"
#   azd provision
#
# Usage (manual):
#   cp provider.conf.json.example provider.conf.json
#   terraform init -backend-config=provider.conf.json
#   terraform apply -var "github_runner_pat=ghp_xxx"
################################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {}

locals {
  common_tags = merge(var.tags, {
    environment = var.environment
    project     = "github-runners"
    managed_by  = "terraform"
  })
}

data "azurerm_client_config" "current" {}

################################################################################
# Resource Group
################################################################################

resource "azurerm_resource_group" "runners" {
  name     = "rg-basileus-runners-${var.environment}"
  location = var.location
  tags     = local.common_tags
}

################################################################################
# Container App Environment (VNet-integrated via Basileus snet-runners subnet)
#
# The subnet lives in rg-basileus-{env} but Azure allows cross-RG subnet
# references. This places runners on the same VNet as the Basileus Container
# Apps, giving them direct access to internal-only services (AgentHost, etc.)
# without requiring VNet peering or public exposure.
################################################################################

resource "azurerm_container_app_environment" "runners" {
  name                     = "cae-basileus-runners-${var.environment}"
  location                 = azurerm_resource_group.runners.location
  resource_group_name      = azurerm_resource_group.runners.name
  infrastructure_subnet_id = var.basileus_runners_subnet_id != "" ? var.basileus_runners_subnet_id : null
  tags                     = local.common_tags
}

################################################################################
# Container Registry
################################################################################

resource "azurerm_container_registry" "runners" {
  name                = "crbasileusrun${var.environment}"
  location            = azurerm_resource_group.runners.location
  resource_group_name = azurerm_resource_group.runners.name
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}

################################################################################
# Managed Identity + Role Assignments
################################################################################

resource "azurerm_user_assigned_identity" "runners" {
  name                = "id-basileus-runners-${var.environment}"
  location            = azurerm_resource_group.runners.location
  resource_group_name = azurerm_resource_group.runners.name
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.runners.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.runners.principal_id
}

################################################################################
# Key Vault + GitHub PAT Secret
################################################################################

resource "azurerm_key_vault" "runners" {
  name                       = "kv-basrun-${var.environment}"
  location                   = azurerm_resource_group.runners.location
  resource_group_name        = azurerm_resource_group.runners.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }

  tags = local.common_tags
}

resource "azurerm_role_assignment" "kv_secrets_officer" {
  scope                = azurerm_key_vault.runners.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "kv_secrets_user" {
  scope                = azurerm_key_vault.runners.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.runners.principal_id
}

resource "azurerm_key_vault_secret" "github_pat" {
  name            = "github-runner-pat"
  value           = var.github_runner_pat
  key_vault_id    = azurerm_key_vault.runners.id
  expiration_date = timeadd(timestamp(), "4380h")

  lifecycle {
    ignore_changes = [value, expiration_date]
  }

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

################################################################################
# Build and Push Runner Image to ACR
#
# Must happen before the Container App Job is created, since Azure validates
# the image exists at creation time. Rebuilds when the Dockerfile changes.
#
# NOTE: The deploy-runner-image.yml CI workflow also rebuilds the image on
# Dockerfile/startup.sh changes pushed to main, so day-to-day image updates
# happen automatically without running terraform apply.
################################################################################

resource "null_resource" "runner_image" {
  depends_on = [azurerm_container_registry.runners]

  triggers = {
    dockerfile_hash = filesha256("${path.module}/Dockerfile")
    startup_hash    = filesha256("${path.module}/startup.sh")
    acr_name        = azurerm_container_registry.runners.name
  }

  provisioner "local-exec" {
    command = "az acr build --registry ${azurerm_container_registry.runners.name} --image basileus/github-runner:${var.runner_image_tag} --file ${path.module}/Dockerfile ${path.module}"
  }
}

################################################################################
# GitHub Actions OIDC — App Registration + Federated Credential
#
# Allows the deploy-runner-image.yml workflow to authenticate to Azure via
# OIDC (no secrets). After `terraform apply`, set the output values as
# GitHub repo variables on lvlup-sw/.github:
#   AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
################################################################################

resource "azuread_application" "github_actions" {
  display_name = "github-actions-runner-deploy-${var.environment}"
}

resource "azuread_service_principal" "github_actions" {
  client_id = azuread_application.github_actions.client_id
}

resource "azuread_application_federated_identity_credential" "github_actions_main" {
  application_id = azuread_application.github_actions.id
  display_name   = "github-actions-main"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_owner}/.github:ref:refs/heads/main"
}

resource "azurerm_role_assignment" "acr_push_github_actions" {
  scope                = azurerm_container_registry.runners.id
  role_definition_name = "AcrPush"
  principal_id         = azuread_service_principal.github_actions.object_id
}

################################################################################
# GitHub Runner Container App Job
################################################################################

resource "azurerm_container_app_job" "github_runner" {
  depends_on = [null_resource.runner_image]
  name                         = "caj-github-runner-${var.environment}"
  location                     = azurerm_resource_group.runners.location
  resource_group_name          = azurerm_resource_group.runners.name
  container_app_environment_id = azurerm_container_app_environment.runners.id

  replica_timeout_in_seconds = 3600
  replica_retry_limit        = 1

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.runners.id]
  }

  registry {
    server   = azurerm_container_registry.runners.login_server
    identity = azurerm_user_assigned_identity.runners.id
  }

  secret {
    name                = "gh-token"
    key_vault_secret_id = azurerm_key_vault_secret.github_pat.versionless_id
    identity            = azurerm_user_assigned_identity.runners.id
  }

  event_trigger_config {
    parallelism              = 1
    replica_completion_count = 1

    scale {
      min_executions = 0
      max_executions = var.max_executions

      rules {
        name             = "github-runner"
        custom_rule_type = "github-runner"
        metadata = {
          githubApiURL              = "https://api.github.com"
          owner                     = var.github_owner
          runnerScope               = "org"
          repos                     = var.github_repos
          targetWorkflowQueueLength = "1"
        }
        authentication {
          secret_name       = "gh-token"
          trigger_parameter = "personalAccessToken"
        }
      }
    }
  }

  template {
    container {
      name   = "runner"
      image  = "${azurerm_container_registry.runners.login_server}/basileus/github-runner:${var.runner_image_tag}"
      cpu    = 2
      memory = "4Gi"

      env {
        name        = "GITHUB_PAT"
        secret_name = "gh-token"
      }

      env {
        name  = "GH_URL"
        value = "https://github.com/${var.github_owner}"
      }

      env {
        name  = "REGISTRATION_TOKEN_API_URL"
        value = "https://api.github.com/orgs/${var.github_owner}/actions/runners/registration-token"
      }
    }
  }

  tags = local.common_tags
}
