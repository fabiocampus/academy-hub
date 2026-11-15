data "github_user" "approvatore" {
  for_each = toset(concat(var.approvatori_infra, var.approvatori_prod))
  username = each.value
}

# Il plan delle PR: nessuna approvazione, token GitHub di sola lettura.
# Esiste già: l'ha creato la prima esecuzione del workflow.
import {
  to = github_repository_environment.infra_plan
  id = "${var.repository}:infra-plan"
}

resource "github_repository_environment" "infra_plan" {
  repository  = github_repository.academy_hub.name
  environment = "infra-plan"
}

# L'apply: solo dal ramo main e solo dopo l'approvazione; credenziali che scrivono.
resource "github_repository_environment" "infra" {
  repository          = github_repository.academy_hub.name
  environment         = "infra"
  can_admins_bypass   = false
  prevent_self_review = false # un solo sviluppatore: approva le proprie modifiche

  reviewers {
    users = [for nome in var.approvatori_infra : tonumber(data.github_user.approvatore[nome].id)]
  }

  # Non "protected_branches": main è protetto da un ruleset, non da una branch
  # protection, e con nessuna branch protection GitHub lascerebbe entrare ogni ramo.
  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }

  # Distruggerlo e ricrearlo perderebbe secret e approvatore.
  lifecycle {
    prevent_destroy = true
  }
}

resource "github_repository_environment_deployment_policy" "infra_main" {
  repository     = github_repository.academy_hub.name
  environment    = github_repository_environment.infra.environment
  branch_pattern = "main"
}

# Rilascio continuo (ADR-0013): environment del workflow rilascio.yml, con le credenziali
# del service principal academy-rilascio scritte da infra/databricks-identita.
# Collaudo: dopo la CI su main, senza approvazione.
resource "github_repository_environment" "collaudo" {
  repository        = github_repository.academy_hub.name
  environment       = "collaudo"
  can_admins_bypass = false

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "github_repository_environment_deployment_policy" "collaudo_main" {
  repository     = github_repository.academy_hub.name
  environment    = github_repository_environment.collaudo.environment
  branch_pattern = "main"
}

# Produzione: solo da main, dopo collaudo e fumo, e dopo l'approvazione.
resource "github_repository_environment" "prod" {
  repository          = github_repository.academy_hub.name
  environment         = "prod"
  can_admins_bypass   = false
  prevent_self_review = false # un solo sviluppatore: approva i propri rilasci

  reviewers {
    users = [for nome in var.approvatori_prod : tonumber(data.github_user.approvatore[nome].id)]
  }

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "github_repository_environment_deployment_policy" "prod_main" {
  repository     = github_repository.academy_hub.name
  environment    = github_repository_environment.prod.environment
  branch_pattern = "main"
}
