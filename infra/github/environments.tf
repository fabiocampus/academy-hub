data "github_user" "approvatore" {
  for_each = toset(var.approvatori_infra)
  username = each.value
}

# Il plan delle PR: nessuna approvazione, credenziali di sola lettura.
resource "github_repository_environment" "infra_plan" {
  repository  = github_repository.academy_hub.name
  environment = "infra-plan"
}

# L'apply: solo da main e solo dopo l'approvazione; credenziali che scrivono.
resource "github_repository_environment" "infra" {
  repository          = github_repository.academy_hub.name
  environment         = "infra"
  can_admins_bypass   = false
  prevent_self_review = false # un solo sviluppatore: approva le proprie modifiche

  reviewers {
    users = [for u in data.github_user.approvatore : tonumber(u.id)]
  }

  deployment_branch_policy {
    protected_branches     = true
    custom_branch_policies = false
  }
}
