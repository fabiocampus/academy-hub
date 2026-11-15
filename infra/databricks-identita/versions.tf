terraform {
  required_version = ">= 1.10"

  # Si applica solo dal PC (ADR-0012): il secret di un service principal si legge
  # con un'API di account, e il service principal del workflow non è admin
  # dell'account (Free Edition non ha l'account console per farlo diventare).
  cloud {
    organization = "academy-hub-studio"

    workspaces {
      name = "academy-databricks-identita"
    }
  }

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.140.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14"
    }
  }
}

# Dal profilo della CLI: DATABRICKS_CONFIG_PROFILE=academy.
provider "databricks" {}

# Token da GITHUB_TOKEN (`gh auth token`).
provider "github" {
  owner = var.proprietario
}
