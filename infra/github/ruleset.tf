locals {
  # I job che una PR deve passare prima del merge. Il workflow dell'infrastruttura
  # non c'è: parte solo quando cambia infra/, quindi non può essere obbligatorio.
  check_obbligatori = [
    "lint",
    "typecheck",
    "test",
    "gitleaks",
    "issue-collegata",
    "immagine",
    "compose",
    "dipendenze",
    "CodeQL (python)",
    "CodeQL (actions)",
    "frontend",
    "CodeQL (javascript-typescript)",
    "e2e",
  ]
  # GitHub Actions: i check devono arrivare da lì, non da un'altra integrazione.
  integrazione_actions = 15368
}

import {
  to = github_repository_ruleset.main_protetto
  id = "${var.repository}:27257261"
}

resource "github_repository_ruleset" "main_protetto" {
  name        = "main protetto"
  repository  = github_repository.academy_hub.name
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  # Nessun bypass, neanche per chi amministra: tutto passa da una PR.

  rules {
    deletion         = true
    non_fast_forward = true

    pull_request {
      required_approving_review_count   = 0
      dismiss_stale_reviews_on_push     = false
      require_code_owner_review         = false
      require_last_push_approval        = false
      required_review_thread_resolution = true
      allowed_merge_methods             = ["squash"]
    }

    required_status_checks {
      strict_required_status_checks_policy = true
      do_not_enforce_on_create             = false

      dynamic "required_check" {
        for_each = local.check_obbligatori
        content {
          context        = required_check.value
          integration_id = local.integrazione_actions
        }
      }
    }
  }
}
