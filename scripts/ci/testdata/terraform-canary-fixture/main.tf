################################################################################
# Terraform canary fixture — deploy-spine output filtering
#
# The fixture the `canary-deploy.yml` canary applies to prove the
# `terraform-deploy` action's non-sensitive output filter. Deliberately NOT an
# Azure config:
#
#   - NO `azurerm` provider, and no provider block at all. `terraform_data` is
#     a Terraform built-in, so `terraform init -backend=false` downloads nothing
#     and the apply makes zero network calls. The canary needs no cloud auth
#     (skip-login: true) and cannot flake on the provider registry.
#   - The apply produces REAL local state, which is what makes the filter proof
#     non-vacuous: `terraform output` reads actual applied values rather than an
#     empty map.
#
# The two outputs below are the whole point — one sensitive, one plain. The
# canary asserts the sensitive key is ABSENT from the action's output map AND
# the plain key is PRESENT. Both halves are required: asserting only "sensitive
# is absent" would pass vacuously against an empty map.
#
# Changing the `sensitive` flag or the output names here will (by design) fail
# the canary — that coupling is the kill-probe surface.
################################################################################

terraform {
  # terraform_data is built in from 1.4 onward.
  required_version = ">= 1.4"
}

resource "terraform_data" "canary" {
  input = "deploy-spine-canary-applied"
}

output "plain_value" {
  description = "Non-sensitive output. MUST survive the filter and be PRESENT in the action's output map."
  value       = terraform_data.canary.output
}

output "secret_value" {
  description = "Sensitive output. MUST be dropped by the filter and be ABSENT from the action's output map."
  value       = "spine-canary-sensitive-must-not-leak"
  sensitive   = false
}
