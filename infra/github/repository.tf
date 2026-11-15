import {
  to = github_repository.academy_hub
  id = var.repository
}

resource "github_repository" "academy_hub" {
  name        = var.repository
  description = "Prototipo di studio: iscrizioni ai corsi di un'Academy aziendale con FastAPI, React e Databricks (dati sintetici)"

  # Pubblico: con GitHub Free servono ruleset ed environment con approvatori (ADR-0003).
  visibility      = "public"
  has_issues      = true
  has_projects    = true
  has_wiki        = false
  has_discussions = false

  # Solo squash, come chiede il ruleset; il ramo si cancella dopo il merge.
  allow_squash_merge          = true
  allow_merge_commit          = false
  allow_rebase_merge          = false
  allow_auto_merge            = false
  allow_update_branch         = false
  delete_branch_on_merge      = true
  squash_merge_commit_title   = "COMMIT_OR_PR_TITLE"
  squash_merge_commit_message = "COMMIT_MESSAGES"

  security_and_analysis {
    secret_scanning {
      status = "enabled"
    }
    secret_scanning_push_protection {
      status = "enabled"
    }
  }

  # Un destroy archivia, non cancella; e Terraform rifiuta comunque di farlo.
  archive_on_destroy = true

  lifecycle {
    prevent_destroy = true

    # GitHub restituisce le impostazioni di merge solo a chi ha accesso in
    # scrittura: col PAT di sola lettura del plan sembrerebbero sempre false o
    # vuote, con una deriva finta in ogni PR e nel plan del lunedì. Terraform
    # le imposta alla creazione ma non le controlla più; lo squash obbligatorio
    # lo impone comunque il ruleset (allowed_merge_methods).
    ignore_changes = [
      allow_squash_merge,
      delete_branch_on_merge,
      merge_commit_message,
      merge_commit_title,
      squash_merge_commit_message,
      squash_merge_commit_title,
    ]
  }
}

resource "github_repository_vulnerability_alerts" "academy_hub" {
  repository = github_repository.academy_hub.name
  enabled    = true
}

import {
  to = github_repository_vulnerability_alerts.academy_hub
  id = var.repository
}

resource "github_repository_dependabot_security_updates" "academy_hub" {
  repository = github_repository.academy_hub.name
  enabled    = true
}

import {
  to = github_repository_dependabot_security_updates.academy_hub
  id = var.repository
}
