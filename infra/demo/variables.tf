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

variable "image_reference" {
  description = "Immutable GHCR image reference selected by the still-open demo artifact decision in issue #124."
  type        = string

  validation {
    condition     = can(regex("^ghcr\\.io/lxndrp/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.image_reference))
    error_message = "image_reference must be an lxndrp GHCR package followed by @sha256:<64 lowercase hexadecimal characters>."
  }
}

variable "container_environment" {
  description = "Non-sensitive runtime settings defined by issue #124; secrets are deliberately not accepted by this stack."
  type        = map(string)
  default     = {}

  validation {
    condition     = alltrue([for name in keys(var.container_environment) : can(regex("^[A-Z_][A-Z0-9_]*$", name))])
    error_message = "container_environment keys must be uppercase environment variable names."
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
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "budget_start_date must be the first day of a month in the form YYYY-MM-01T00:00:00Z."
  }
}

variable "budget_end_date" {
  description = "End of the budget period as RFC3339 UTC, chosen explicitly for reproducible plans."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-01T00:00:00Z$", var.budget_end_date)) && timecmp(var.budget_end_date, var.budget_start_date) > 0
    error_message = "budget_end_date must be a first-of-month RFC3339 timestamp later than budget_start_date."
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
