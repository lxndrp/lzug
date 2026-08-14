variable "azure_subscription_id" {
  description = "Azure subscription that contains the isolated public demo. This identifier is not a secret."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.azure_subscription_id))
    error_message = "azure_subscription_id must be a UUID."
  }
}

variable "location" {
  description = "European Azure region used for all regional demo resources."
  type        = string
  default     = "westeurope"

  validation {
    condition     = contains(["westeurope", "northeurope", "germanywestcentral", "swedencentral", "francecentral"], var.location)
    error_message = "location must be one of the approved European Azure regions."
  }
}

variable "name_prefix" {
  description = "Stable lowercase prefix for the isolated demo resources."
  type        = string
  default     = "lzug-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name_prefix))
    error_message = "name_prefix must contain 3 to 20 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "demo_artifact_pair" {
  description = "Previously verified immutable demo app/seed pair and its shared product, schema, and seed binding."
  type = object({
    app_image          = string
    seed_image         = string
    product_tag        = string
    product_commit     = string
    schema_fingerprint = string
    seed_revision      = string
  })

  validation {
    condition = (
      can(regex("^ghcr\\.io/lxndrp/lzug-demo-app@sha256:[0-9a-f]{64}$", var.demo_artifact_pair.app_image)) &&
      can(regex("^ghcr\\.io/lxndrp/lzug-demo-seed@sha256:[0-9a-f]{64}$", var.demo_artifact_pair.seed_image)) &&
      can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+([+-][0-9A-Za-z.-]+)?$", var.demo_artifact_pair.product_tag)) &&
      can(regex("^[0-9a-f]{40}$", var.demo_artifact_pair.product_commit)) &&
      can(regex("^[0-9a-f]{64}$", var.demo_artifact_pair.schema_fingerprint)) &&
      can(regex("^[0-9a-f]{64}$", var.demo_artifact_pair.seed_revision))
    )
    error_message = "demo_artifact_pair must contain the two canonical digest-pinned demo packages and valid shared product, schema, and seed identifiers."
  }
}

variable "container_environment" {
  description = "Non-sensitive runtime settings defined by issue #124; secrets are deliberately not accepted by this stack."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for name in keys(var.container_environment) :
      can(regex("^[A-Z_][A-Z0-9_]*$", name)) && name != "LZUG_DATA_DIR"
    ])
    error_message = "container_environment keys must be uppercase environment variable names and must not replace LZUG_DATA_DIR."
  }
}

variable "container_port" {
  description = "Single internal HTTP port exposed through managed Container Apps ingress."
  type        = number
  default     = 8000

  validation {
    condition     = var.container_port >= 1024 && var.container_port <= 65535
    error_message = "container_port must be an unprivileged TCP port."
  }
}

variable "budget_amount_eur" {
  description = "Hard-to-miss monthly cost threshold in EUR; the budget alerts but does not stop resources automatically."
  type        = number

  validation {
    condition     = var.budget_amount_eur > 0 && var.budget_amount_eur <= 100
    error_message = "budget_amount_eur must be greater than 0 and no more than 100."
  }
}

variable "budget_contact_emails" {
  description = "Maintainer addresses that receive actual and forecast budget alerts."
  type        = list(string)

  validation {
    condition     = length(var.budget_contact_emails) > 0 && alltrue([for email in var.budget_contact_emails : can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", email))])
    error_message = "budget_contact_emails must contain at least one valid email address."
  }
}

variable "budget_start_date" {
  description = "First day of the budget period as RFC3339 UTC, chosen explicitly for reproducible plans."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-01T00:00:00Z$", var.budget_start_date)) && can(timecmp(var.budget_start_date, "1970-01-01T00:00:00Z"))
    error_message = "budget_start_date must be a valid first-of-month RFC3339 UTC timestamp in the form YYYY-MM-01T00:00:00Z."
  }
}

variable "budget_end_date" {
  description = "End of the budget period as RFC3339 UTC, chosen explicitly for reproducible plans."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00Z$", var.budget_end_date)) && can(timecmp(var.budget_end_date, var.budget_start_date)) && timecmp(var.budget_end_date, var.budget_start_date) > 0
    error_message = "budget_end_date must be a valid RFC3339 UTC timestamp later than budget_start_date."
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
  default     = "lxndrp"
}

variable "github_repository" {
  description = "Repository in which the protected demo environment is managed."
  type        = string
  default     = "lzug"
}

variable "tags" {
  description = "Additional non-sensitive Azure tags."
  type        = map(string)
  default     = {}
}
