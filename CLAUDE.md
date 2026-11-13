# Academy Hub

Prototipo di studio: iscrizioni ai corsi di un'Academy aziendale (parte transazionale) e report con controlli di qualità su Databricks (parte analitica). Leggi `docs/visione.md` e `CONTEXT.md` prima di lavorare sul dominio.

## Stato

Fase 1 (visione e backlog). Non c'è ancora codice: comandi di build, test e avvio arrivano con la fase 2.

## Regole

- Il repository è **pubblico**: nessun segreto, token, email reale o dato reale nel codice, nei test, nelle issue o nei messaggi di commit. Solo dati sintetici.
- Nessun push su `main`: ogni modifica passa da una pull request collegata a una issue (`Closes #n`).
- Ogni modifica di comportamento ha un test; i criteri di accettazione delle storie diventano test.
- Usa i termini di `CONTEXT.md`; le entità di dominio hanno nomi italiani anche nel codice.
- Aggiorna documentazione e ADR nella stessa PR della modifica.
- Non toccare `infra/` senza richiesta esplicita.
- Commit in formato Conventional Commits.

## Agent skills

### Issue tracker

GitHub Issues con sub-issue e una board in GitHub Projects. Vedi `docs/agents/issue-tracker.md`.

### Triage labels

Vocabolario predefinito: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. Vedi `docs/agents/triage-labels.md`.

### Domain docs

Contesto singolo: `CONTEXT.md` + `docs/adr/` nella radice. Vedi `docs/agents/domain.md`.
