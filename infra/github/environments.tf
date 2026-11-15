data "github_user" "approvatore" {
  for_each = toset(var.approvatori_infra)
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
    users = [for u in data.github_user.approvatore : tonumber(u.id)]
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
