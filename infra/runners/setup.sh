#!/usr/bin/env bash
# =============================================================================
# setup.sh - Pre-provisioning hook for standalone runner deployment
# =============================================================================
# Validates prerequisites and bootstraps Terraform state backend before azd
# runs terraform. Non-interactive — safe to run from azd hooks and CI.
#
# What it does:
#   1. Checks Azure CLI authentication
#   2. Bootstraps Terraform state backend (storage account) if needed
#   3. Auto-detects Basileus runners subnet for VNet integration
#
# Prerequisites:
#   azd env set TF_VAR_github_runner_pat "ghp_xxx"
#   Deploy Basileus infra first (azd up in basileus/) for VNet integration
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCATION="${AZURE_LOCATION:-canadacentral}"

echo "==> GitHub Runners: pre-provisioning checks"

# --- Azure CLI auth check ---
echo "  -> Checking Azure CLI authentication..."
if ! az account show &>/dev/null; then
    echo "ERROR: Not logged in to Azure CLI. Run 'az login' first." >&2
    exit 1
fi
SUBSCRIPTION=$(az account show --query name -o tsv)
echo "  -> Authenticated (subscription: ${SUBSCRIPTION})"

# --- Generate provider.conf.json dynamically (matches basileus pattern) ---
ENVIRONMENT="${AZURE_ENV_NAME:-dev}"
BACKEND_CONF="${SCRIPT_DIR}/provider.conf.json"
if [ ! -f "$BACKEND_CONF" ]; then
    echo "  -> Generating provider.conf.json for environment '${ENVIRONMENT}'..."
    cat > "$BACKEND_CONF" <<EOF
{
  "resource_group_name": "rg-basileus-runners-tfstate-${ENVIRONMENT}",
  "storage_account_name": "stbasileusrunstate${ENVIRONMENT}",
  "container_name": "tfstate",
  "key": "github-runners.terraform.tfstate"
}
EOF
fi

# --- Bootstrap Terraform state backend ---
RG_STATE=$(jq -r '.resource_group_name' "$BACKEND_CONF")
SA_NAME=$(jq -r '.storage_account_name' "$BACKEND_CONF")
CONTAINER=$(jq -r '.container_name' "$BACKEND_CONF")

echo "  -> Checking Terraform state backend..."
if az storage account show --name "$SA_NAME" --resource-group "$RG_STATE" &>/dev/null; then
    echo "  -> State backend exists (${SA_NAME} in ${RG_STATE})"
else
    echo "  -> Creating Terraform state backend..."

    echo "    -> Resource group: ${RG_STATE}"
    az group create \
        --name "$RG_STATE" \
        --location "$LOCATION" \
        --output none

    echo "    -> Storage account: ${SA_NAME}"
    az storage account create \
        --name "$SA_NAME" \
        --resource-group "$RG_STATE" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        --output none

    echo "    -> Blob container: ${CONTAINER}"
    az storage container create \
        --name "$CONTAINER" \
        --account-name "$SA_NAME" \
        --auth-mode login \
        --output none

    echo "  -> State backend created."
fi

# --- Auto-detect Basileus runners subnet ---
BASILEUS_RG="rg-basileus-${ENVIRONMENT}"
BASILEUS_VNET="vnet-basileus-${ENVIRONMENT}"
SUBNET_NAME="snet-runners"

CURRENT_SUBNET="$(azd env get-value TF_VAR_basileus_runners_subnet_id 2>/dev/null || true)"
if [ -z "$CURRENT_SUBNET" ]; then
    echo "  -> Looking up ${SUBNET_NAME} in ${BASILEUS_VNET}..."
    SUBNET_ID=$(az network vnet subnet show \
        --resource-group "$BASILEUS_RG" \
        --vnet-name "$BASILEUS_VNET" \
        --name "$SUBNET_NAME" \
        --query id -o tsv 2>/dev/null || true)
    if [ -n "$SUBNET_ID" ]; then
        echo "  -> Found subnet: ${SUBNET_ID}"
        azd env set TF_VAR_basileus_runners_subnet_id "$SUBNET_ID"
    else
        echo "  -> WARNING: Basileus subnet not found. Runners will deploy without VNet integration." >&2
        echo "    Deploy Basileus infra first (azd up in basileus/) or set manually:" >&2
        echo "    azd env set TF_VAR_basileus_runners_subnet_id <subnet-id>" >&2
    fi
else
    echo "  -> Basileus subnet already set in azd env"
fi

echo "==> Pre-provisioning checks passed."
