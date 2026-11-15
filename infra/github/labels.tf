locals {
  label = {
    # Gerarchia del backlog (docs/agents/issue-tracker.md)
    "type:epic"    = { colore = "5319e7", descrizione = "Obiettivo ampio, scomposto in feature" }
    "type:feature" = { colore = "1d76db", descrizione = "Insieme coerente di user story" }
    "type:story"   = { colore = "0e8a16", descrizione = "Funzione vista da un utente" }
    "type:bug"     = { colore = "d73a4a", descrizione = "Comportamento diverso da quello atteso" }
    "type:chore"   = { colore = "c5def5", descrizione = "Attività tecnica" }

    # Triage (docs/agents/triage-labels.md)
    "needs-triage"    = { colore = "fbca04", descrizione = "Da valutare" }
    "needs-info"      = { colore = "fef2c0", descrizione = "In attesa di informazioni" }
    "ready-for-agent" = { colore = "0e8a16", descrizione = "Specificata, pronta per un agente" }
    "ready-for-human" = { colore = "bfd4f2", descrizione = "Richiede lavoro umano" }
    "wontfix"         = { colore = "ffffff", descrizione = "Non verrà fatta" }

    # Regole di business toccate
    "regola:R1" = { colore = "f9d0c4", descrizione = "Una iscrizione attiva per persona ed edizione" }
    "regola:R2" = { colore = "f9d0c4", descrizione = "Solo il responsabile diretto approva" }
    "regola:R3" = { colore = "f9d0c4", descrizione = "Mai oltre la capienza" }
    "regola:R4" = { colore = "f9d0c4", descrizione = "Promozione dalla lista d'attesa" }
    "regola:R5" = { colore = "f9d0c4", descrizione = "Scadenza di annullamento" }
    "regola:R6" = { colore = "f9d0c4", descrizione = "Audit di ogni cambio di stato" }
    "regola:R7" = { colore = "f9d0c4", descrizione = "Transizioni non previste rifiutate" }

    # Quelle che Dependabot crea da sé: gestite qui, così il plan non le vede come deriva.
    "accessibility"                 = { colore = "f143ab", descrizione = "Barrier affecting people with disabilities" }
    "dependencies"                  = { colore = "0366d6", descrizione = "Pull requests that update a dependency file" }
    "docker"                        = { colore = "21ceff", descrizione = "Pull requests that update docker code" }
    "docker_compose"                = { colore = "E5F2FC", descrizione = "Pull requests that update docker_compose code" }
    "devcontainers_package_manager" = { colore = "2753E3", descrizione = "Pull requests that update devcontainers_package_manager code" }
    "javascript"                    = { colore = "168700", descrizione = "Pull requests that update javascript code" }
  }
}

import {
  for_each = local.label
  to       = github_issue_label.label[each.key]
  id       = "${var.repository}:${each.key}"
}

# Una risorsa per label, non github_issue_labels: quella cancellerebbe le label
# create da altri (Dependabot) prima che entrino qui.
resource "github_issue_label" "label" {
  for_each = local.label

  repository  = github_repository.academy_hub.name
  name        = each.key
  color       = each.value.colore
  description = each.value.descrizione
}
