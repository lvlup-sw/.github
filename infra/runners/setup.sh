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
#
# Prerequisites:
#   azd env set TF_VAR_github_runner_pat "ghp_xxx"
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCATION="${AZURE_LOCATION:-eastus2}"

echo "==> GitHub Runners: pre-provisioning checks"

# --- Azure CLI auth check ---
echo "  -> Checking Azure CLI authentication..."
if ! az account show &>/dev/null; then
    echo "ERROR: Not logged in to Azure CLI. Run 'az login' first." >&2
    exit 1
fi
SUBSCRIPTION=$(az account show --query name -o tsv)
echo "  -> Authenticated (subscription: ${SUBSCRIPTION})"

# --- Bootstrap Terraform state backend ---
# Read backend config to get expected resource names
BACKEND_CONF="${SCRIPT_DIR}/provider.conf.json"
RG_STATE=$(python3 -c "import json; print(json.load(open('${BACKEND_CONF}'))['resource_group_name'])")
SA_NAME=$(python3 -c "import json; print(json.load(open('${BACKEND_CONF}'))['storage_account_name'])")
CONTAINER=$(python3 -c "import json; print(json.load(open('${BACKEND_CONF}'))['container_name'])")

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

echo "==> Pre-provisioning checks passed."
