################################################################################
# Variables
################################################################################

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region for all resources. Must match the Basileus VNet region when using VNet integration."
  type        = string
  default     = "canadacentral"
}

variable "basileus_runners_subnet_id" {
  description = "Subnet ID for VNet-integrated runner CAE. Get from Basileus infra: terraform output -raw runners_subnet_id"
  type        = string
  default     = ""
}

variable "github_runner_pat" {
  description = "GitHub PAT with repo and workflow scopes for runner registration. Set via TF_VAR_github_runner_pat — never commit to tfvars files."
  type        = string
  sensitive   = true
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  default     = "lvlup-sw"
}

variable "github_repos" {
  description = "Comma-separated list of GitHub repositories to monitor for workflow jobs"
  type        = string
  default     = "basileus,.github,exarchos,valkyrie,bifrost,lvlup-build"
}

variable "runner_image_tag" {
  description = "Tag for the GitHub runner container image"
  type        = string
  default     = "latest"
}

variable "max_executions" {
  description = "Maximum concurrent runner job executions"
  type        = number
  default     = 8
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
