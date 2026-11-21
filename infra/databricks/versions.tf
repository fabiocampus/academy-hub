terraform {
  required_version = ">= 1.10"

  # Stesso schema di infra/github: stato su HCP Terraform Free, execution mode
  # locale (ADR-0012).
  cloud {
    organization = "academy-hub-studio"

    workspaces {
      name = "academy-databricks"
    }
  }

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.144.0"
    }
  }
}

# Workspace e credenziali dall'ambiente, mai dai file (repository pubblico):
# dal PC DATABRICKS_CONFIG_PROFILE=academy, nel workflow DATABRICKS_HOST,
# DATABRICKS_CLIENT_ID e DATABRICKS_CLIENT_SECRET del service principal
# academy-terraform, scritti da infra/databricks-identita.
provider "databricks" {}
