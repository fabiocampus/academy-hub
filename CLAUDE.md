# Academy Hub

Prototipo di studio: iscrizioni ai corsi di un'Academy aziendale (parte transazionale) e report con controlli di qualità su Databricks (parte analitica). Leggi `docs/visione.md` e `CONTEXT.md` prima di lavorare sul dominio.

## Stato

Fase 5 (API a livelli), in tre PR (issue #49): errori RFC 9457, ETag/If-Match, contratto OpenAPI versionato, corsi, edizioni e catalogo; flusso delle iscrizioni (richiesta idempotente, approvazione del responsabile diretto, conferma, annullamento, audit); promozione dalla lista d'attesa nella stessa transazione, cancellazione dell'edizione e job di sistema (ADR-0007). Convenzioni in `docs/adr/0005-convenzioni-dell-api.md`.

Fase 6 (identità e sicurezza, issue #36): identità da token OIDC di Keycloak in locale e da `X-Forwarded-Email` su Databricks Apps, ruoli dal database, persona trovata per email (ADR-0008). Seconda PR (issue #56): matrice di autorizzazione rotta × profilo (`backend/tests/test_autorizzazione.py`: una rotta nuova senza la sua riga fa fallire i test), pip-audit e CodeQL in CI, threat model STRIDE in `docs/threat-model.md`.

## Ambiente locale

Dalla radice del repository, senza altri passaggi (il `.env` è facoltativo, vedi `.env.example`):

```bash
docker compose up -d --build --wait   # db, migrazioni, demo, keycloak, otel-lgtm, backend, job
python scripts/fumo_identita.py       # token veri da Keycloak e flusso richiesta -> approvazione -> conferma
docker compose down                   # -v per cancellare anche i dati
```

Porte su 127.0.0.1: backend 8000 (`/health`, `/docs`), Keycloak 8080 (console admin/admin; realm `academy` da `keycloak/realm-academy.json`, utenti di prova `dipendente`, `responsabile`, `dirigente`, `admin`, `docente`, `esterna` con password uguale al nome), Grafana 3000, PostgreSQL 5432, OTLP 4317/4318. In alternativa c'è il dev container (`.devcontainer/`).

La configurazione arriva solo da variabili d'ambiente: quelle del backend hanno prefisso `ACADEMY_` (`backend/src/academy_hub/config.py`).

## Comandi

Tutti dentro `backend/` (Python 3.11, come Databricks Apps, fissato in `backend/.python-version`):

```bash
uv sync                      # crea .venv e installa le dipendenze
uv run pytest                # tutti i test (quelli `integrazione` avviano PostgreSQL con Testcontainers: serve Docker)
uv run pytest -m "not integrazione"   # solo i test veloci, senza Docker
uv run python -m academy_hub.db.migrazioni   # migra il PostgreSQL locale (o ACADEMY_DATABASE_URL)
uv run python -m academy_hub.job              # una passata del job di sistema (--ogni N per ripeterla)
uv run python -m academy_hub.db.demo          # dati demo (persone degli utenti Keycloak, catalogo), solo in locale
uv run python -m academy_hub.contratto        # rigenera backend/contratto/ dopo un cambio dell'API (aumenta VERSIONE_API)
uv run ruff check --fix      # lint
uv run ruff format           # formattazione
uv run pyright               # controllo dei tipi (strict)
uv run pre-commit install    # una volta per clone: hook pre-commit (ruff, gitleaks, ...)
uv run pre-commit run --all-files
```

Dopo ogni modifica a un file `.py` del backend l'hook `.claude/hooks/dopo_modifica.py` lancia ruff e i test veloci (non quelli `integrazione`); se fallisce, correggi prima di proseguire. Prima della PR lancia anche `uv run pytest` completo.

## Architettura

- `backend/src/academy_hub/`: pacchetto Python. Livelli: router (FastAPI) → servizi (regole di business, autorizzazione) → repository (accesso ai dati). Niente regole nelle rotte, niente SQL fuori dai repository.
  - `api/`: rotte FastAPI (`rotte/`), schemi Pydantic, errori RFC 9457, dipendenze (transazione per richiesta, attore, `If-Match`), provider d'identità (`identita.py`: oidc, databricks, provvisoria; scelto da `ACADEMY_IDENTITA`). `VERSIONE_API` in `api/__init__.py`.
  - `dominio/`: stati dell'iscrizione e transizioni (R7), ruoli, attore, errori di dominio con il loro `tipo`, calendario di Roma; Python puro, senza database.
  - `db/`: modelli SQLAlchemy (`modelli.py`) e migrazioni Alembic (`schema/versions/`). Lo schema cambia solo con una migrazione. Vedi `docs/database.md`.
  - `repository/`: le query, con i lock `FOR UPDATE`. Ordine dei lock: prima l'edizione, poi le sue iscrizioni (ADR-0004).
  - `servizi/`: le regole. Ogni cambio di stato di un'iscrizione passa da un solo punto che verifica la transizione e scrive l'audit (R6). Ogni posto liberato passa da `promuovi_dalla_lista` nella stessa transazione (R4).
  - `job.py`: job di sistema (scadenza all'inizio dell'edizione, rete di sicurezza della promozione), una transazione per edizione (ADR-0007).
- `backend/contratto/`: contratto OpenAPI e impronte per versione; `tests/test_contratto.py` fallisce se l'API cambia senza aumentare la versione.
- `backend/tests/`: test pytest. I test HTTP usano la fixture `client` (TestClient sull'app collegata al database di test, identità provvisoria `X-Persona-Id`) e `tests/api.py`; i test del token usano `tests/oidc.py` (chiave RSA di test). `dati.py` crea dati sintetici; `conftest.py` avvia PostgreSQL con la stessa immagine di docker compose e applica le migrazioni.
- `backend/Dockerfile`: multi-stage con uv, runtime non root (uid 10001).
- `.github/workflows/`: `ci.yml` (lint, typecheck, test, dipendenze con pip-audit su `uv.lock`, immagine + Trivy, compose, gitleaks), `codeql.yml` (CodeQL su Python e Actions) e `pr-issue.yml` (la PR deve collegare una issue). Sono status check obbligatori del ruleset su `main`. Sul repository sono attivi secret scanning con push protection, avvisi e aggiornamenti di sicurezza di Dependabot.

## Flusso di lavoro

1. Issue → branch `<tipo>/<n>-<descrizione>` da `main`.
2. Test prima del codice per i criteri di accettazione.
3. Comandi verdi in locale, poi PR con `Closes #n` e l'elenco di che cosa hai eseguito.
4. Rilettura con il subagent `revisore` (`.claude/agents/revisore.md`) prima del merge (squash).

## Regole

- Il repository è **pubblico**: nessun segreto, token, email reale o dato reale nel codice, nei test, nelle issue o nei messaggi di commit. Solo dati sintetici.
- Nessun push su `main` (lo impedisce anche il ruleset): ogni modifica passa da una pull request collegata a una issue (`Closes #n`).
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
