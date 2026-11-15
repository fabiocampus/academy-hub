# Come contribuire

Il repository è **pubblico**: nessun segreto, token, email reale o dato reale nel codice, nei test, nelle issue o nei commit. Solo dati sintetici (`@esempio.test`, `@academy.example`, `example.org`).

## Prima di cominciare

1. Leggi [CONTEXT.md](CONTEXT.md) (termini del dominio: usali anche nel codice, in italiano) e [docs/architettura.md](docs/architettura.md).
2. Avvia l'ambiente locale come spiegato nel [README](README.md).
3. Una volta per clone, da `backend/`: `uv sync && uv run pre-commit install` (ruff, gitleaks e altri controlli a ogni commit).

## Il flusso

1. **Issue.** Ogni modifica parte da una issue (modelli in `.github/ISSUE_TEMPLATE/`). Una storia è pronta quando rispetta la Definition of Ready di [docs/processo.md](docs/processo.md): criteri di accettazione *Dato / Quando / Allora*, regole R1–R7 toccate, impatti su schema, contratto e permessi.
2. **Branch** da `main`: `<tipo>/<numero-issue>-<descrizione>`, ad esempio `feat/12-lista-attesa`.
3. **Test prima del codice.** Ogni criterio di accettazione diventa un test, compresi i casi vietati. Un test verifica l'effetto (corpo della risposta, righe nel database), non solo che non ci siano errori.
4. **Commit** in formato [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`…).
5. **Pull request** con `Closes #n` (senza, il check `issue-collegata` fallisce) e l'elenco dei comandi eseguiti, secondo il modello. Merge solo squash, con tutti i check obbligatori verdi e le discussioni risolte: lo impone il ruleset su `main`, anche all'amministratore.
6. **Rilascio.** Dopo il merge la modifica va da sola in collaudo; la produzione richiede un'approvazione nell'environment `prod`. Una storia è *Fatto* solo dopo il collaudo (Definition of Done).

## Compiti ricorrenti

Le procedure passo per passo stanno in `.claude/skills/` (le usa l'agente, valgono per tutti):

- **Cambiare lo schema del database**: [nuova-migrazione](.claude/skills/nuova-migrazione/SKILL.md). Migrazioni Alembic compatibili con la versione precedente (expand/contract, ADR-0013).
- **Aggiungere o cambiare una rotta dell'API**: [nuova-rotta](.claude/skills/nuova-rotta/SKILL.md). Test, riga nella matrice di autorizzazione, `VERSIONE_API` e contratto rigenerato, client del frontend.
- **Una funzione da accendere per ambiente**: feature flag, ADR-0014.
- **Infrastruttura** (`infra/`): solo con una issue che lo chiede; il plan compare nella PR, l'apply va approvato ([infra/README.md](infra/README.md)).

## Controlli prima della PR

```bash
(cd backend  && uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest)
(cd frontend && npm run lint && npm run formato && npm run tipi && npm test)
(cd analisi  && uv run ruff check && uv run pyright && uv run pytest)   # se tocchi analisi/
```

Gli end-to-end (`npm run e2e` in `frontend/`, con docker compose acceso) girano comunque in CI.

## Documentazione

Si aggiorna nella stessa PR della modifica: contratto OpenAPI, `docs/`, `CONTEXT.md` per un termine nuovo, un ADR in `docs/adr/` (numerato, stesso formato degli altri) per ogni scelta non ovvia o che sarebbe costoso cambiare.

## Con un agente di programmazione

Il progetto è stato sviluppato con Claude Code: le istruzioni per l'agente sono in [CLAUDE.md](CLAUDE.md), le impostazioni e l'hook in `.claude/`, la scelta di `gh` al posto del server MCP di GitHub in ADR-0019. Un agente segue le stesse regole di una persona: PR, test, revisione (subagent `revisore`) prima del merge.
