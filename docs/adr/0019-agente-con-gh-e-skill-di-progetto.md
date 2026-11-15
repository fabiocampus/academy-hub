# ADR-0019 · L'agente usa `gh` e le skill di progetto

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 13 (issue #116). Il progetto è stato scritto con un agente di programmazione (Claude Code). Per leggere issue, PR e run c'erano due strade: il server MCP di GitHub collegato all'agente, oppure la CLI `gh` lanciata dall'agente. Alcuni compiti tornano a ogni storia (una migrazione, una rotta nuova con i suoi test) e l'agente ha sbagliato più volte gli stessi passi: contratto non rigenerato, riga mancante nella matrice di autorizzazione, migrazione non compatibile con il rilascio precedente.

## Decisione

1. **`gh` al posto del server MCP di GitHub.** `gh` è già installato e autenticato per gli umani, le stesse chiamate le può ripetere chiunque dal terminale, i permessi dell'agente si regolano comando per comando in `.claude/settings.json` (lettura consentita; `git push`, `gh pr create`, `gh pr merge`, `gh api` con conferma) e non serve un secondo token da conservare. Il server MCP darebbe chiamate tipizzate ma un'altra credenziale, un altro processo e permessi meno granulari.
2. **Skill di progetto** in `.claude/skills/` per i compiti ripetuti: `nuova-migrazione` e `nuova-rotta`. Ognuna elenca i passi nell'ordine, i comandi di verifica e gli errori già visti. Si aggiunge una skill quando lo stesso errore dell'agente si ripete.
3. **`CLAUDE.md` corto sulla storia, lungo sulle regole**: lo stato rimanda a issue e ADR; la sezione *Lezioni imparate* tiene gli errori che non si vedono dal codice (comportamenti di Databricks serverless, Windows, rilascio).
4. Restano: subagent `revisore` prima del merge, hook `dopo_modifica.py` (ruff e test veloci dopo ogni modifica a un `.py` del backend), ruleset che rifiuta push su `main` anche all'amministratore.

## Conseguenze

- Un contributore senza agente segue gli stessi passi: le skill sono anche documentazione (`CONTRIBUTING.md` le richiama).
- Le skill vanno tenute allineate al codice: un cambio di convenzione (ADR-0005, ADR-0013) va riportato nella skill nella stessa PR.
- Senza MCP l'agente legge l'output testuale di `gh`; per i dati strutturati usa `--json` e `--jq`.
