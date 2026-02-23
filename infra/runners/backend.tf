################################################################################
# Remote State Backend
#
# When using azd: backend is configured automatically by azd provision.
# When using terraform directly: pass -backend-config=provider.conf.json
################################################################################

terraform {
  backend "azurerm" {}
}
