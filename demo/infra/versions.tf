terraform {
  required_version = "= 1.12.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
    github = {
      source  = "integrations/github"
      version = "= 6.13.0"
    }
  }

  backend "azurerm" {}
}
