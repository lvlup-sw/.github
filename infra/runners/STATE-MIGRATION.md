# Terraform State Migration: basileus → .github

Runner infrastructure moved from `basileus/infra/runners/` to `.github/infra/runners/`. Azure resource names are unchanged — only the state backend key changes. This guide migrates state without destroying/recreating resources.

## Prerequisites

- Azure CLI authenticated (`az login`)
- Terraform >= 1.5.0
- Access to the state storage account (`stbasileusrunstatedev` in `rg-basileus-runners-tfstate-dev`)

## Steps

### 1. Export state from the old location

```bash
cd ~/Documents/code/lvlup-sw/basileus/infra/runners
terraform init -backend-config=provider.conf.json
terraform state pull > /tmp/runners-state.json
```

### 2. Configure the new backend

```bash
cd ~/Documents/code/lvlup-sw/.github/infra/runners
cp provider.conf.json.example provider.conf.json
# Edit provider.conf.json with real values (storage account credentials)
# The state key is already updated to "github-runners.terraform.tfstate"
```

### 3. Initialize and push state

```bash
terraform init -backend-config=provider.conf.json
# When prompted about migrating state, answer "no" — we'll push manually

terraform state push /tmp/runners-state.json
```

If `state push` rejects due to serial number, use `-force`:

```bash
terraform state push -force /tmp/runners-state.json
```

### 4. Verify — plan must show no infrastructure changes

```bash
terraform plan -var "github_runner_pat=placeholder"
```

Expected output should show **only** new resources from the OIDC additions:
- `azuread_application.github_actions` — new
- `azuread_service_principal.github_actions` — new
- `azuread_application_federated_identity_credential.github_actions_main` — new
- `azurerm_role_assignment.acr_push_github_actions` — new

All existing resources (resource group, ACR, container app job, key vault, etc.) should show **no changes**. If the plan wants to destroy/recreate any existing resource, stop and investigate.

### 5. Apply to create OIDC resources

```bash
terraform apply -var "github_runner_pat=$(az keyvault secret show --vault-name kv-basrun-dev --name github-runner-pat --query value -o tsv)"
```

### 6. Set GitHub repo variables from outputs

```bash
gh variable set AZURE_CLIENT_ID \
  --repo lvlup-sw/.github \
  --body "$(terraform output -raw github_actions_client_id)"

gh variable set AZURE_TENANT_ID \
  --repo lvlup-sw/.github \
  --body "$(terraform output -raw azure_tenant_id)"

gh variable set AZURE_SUBSCRIPTION_ID \
  --repo lvlup-sw/.github \
  --body "$(terraform output -raw azure_subscription_id)"
```

### 7. Verify the deploy workflow

Trigger a manual run to confirm OIDC works end-to-end:

```bash
gh workflow run deploy-runner-image.yml --repo lvlup-sw/.github
```

Check the run succeeds: `az acr repository show-tags --name crbasileusrundev --repository basileus/github-runner`

### 8. Clean up old state key (optional)

After confirming everything works, delete the old state blob:

```bash
az storage blob delete \
  --account-name stbasileusrunstatedev \
  --container-name tfstate \
  --name basileus-runners.terraform.tfstate \
  --auth-mode login
```

### 9. Remove old infra directory from basileus

Delete `basileus/infra/runners/` and commit.

## Rollback

If something goes wrong, the old state blob still exists at `basileus-runners.terraform.tfstate` (until step 8). Re-initialize in the basileus directory:

```bash
cd ~/Documents/code/lvlup-sw/basileus/infra/runners
terraform init -backend-config=provider.conf.json
terraform plan -var "github_runner_pat=placeholder"
```
