terraform {
  required_version = ">= 1.10"

  # Stato su HCP Terraform Free, con execution mode locale: plan e apply girano
  # dove si lancia Terraform (PC o runner), HCP tiene stato e lock (ADR-0012).
  cloud {
    organization = "academy-hub-studio"

    workspaces {
      name = "academy-github"
    }
  }

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
  }
}

# Il token arriva da GITHUB_TOKEN: dal PC `gh auth token`, nel workflow il secret
# dell'environment (sola lettura per il plan, amministrazione per l'apply).
provider "github" {
  owner = var.proprietario
}
