# Academy Hub

Prototipo di studio: iscrizioni ai corsi di un'Academy aziendale (parte transazionale) e report con controlli di qualità su Databricks (parte analitica). Leggi `docs/visione.md` e `CONTEXT.md` prima di lavorare sul dominio.

## Stato

Fase 5 (API a livelli), in tre PR (issue #49): errori RFC 9457, ETag/If-Match, contratto OpenAPI versionato, corsi, edizioni e catalogo; flusso delle iscrizioni (richiesta idempotente, approvazione del responsabile diretto, conferma, annullamento, audit); promozione dalla lista d'attesa nella stessa transazione, cancellazione dell'edizione e job di sistema (ADR-0007). Convenzioni in `docs/adr/0005-convenzioni-dell-api.md`.

Fase 6 (identità e sicurezza, issue #36): identità da token OIDC di Keycloak in locale e da `X-Forwarded-Email` su Databricks Apps, ruoli dal database, persona trovata per email (ADR-0008). Seconda PR (issue #56): matrice di autorizzazione rotta × profilo (`backend/tests/test_autorizzazione.py`: una rotta nuova senza la sua riga fa fallire i test), pip-audit e CodeQL in CI, threat model STRIDE in `docs/threat-model.md`.

Fase 7 (frontend, issue #59), in tre PR: A) base in `frontend/` (React, Vite, Mantine, React Query, client dal contratto, login OIDC con PKCE, catalogo; ADR-0009); B) mie iscrizioni con annullamento, richiesta dal catalogo, approvazioni (issue #62), poi gestione di corsi, edizioni e iscrizioni dell'edizione per `admin_academy` (issue #64, elenchi nuovi nel contratto 1.5.0, modifiche con ETag/If-Match); C) build servita da FastAPI nello stesso processo, end-to-end con Playwright su docker compose e axe, bundle diviso per pagina (issue #66).

Fase 8 (Databricks, issue #68), in due PR: A) l'App su Lakebase (issue #69): bundle `databricks.yml` con target `collaudo` e `prod`, un progetto Lakebase con un branch per ambiente, password del database = token OAuth per connessione, schema `academy`, avvio con migrazioni e persona amministratrice (ADR-0010); B) Unity Catalog e identità dell'utente (issue #73): cataloghi `academy_collaudo`/`academy_prod` con `bronze`/`silver`/`gold` nel bundle, report `GET /api/v1/report/iscrizioni-per-corso` letto con il token dell'utente (`X-Forwarded-Access-Token`, scope `sql`) su un SQL warehouse, porta `LettoreReport` in `report.py` (ADR-0011).

Fase 9 (infrastruttura come codice, issue #75), in due PR: A) Terraform per GitHub in `infra/github/` (repository, ruleset, environment `infra`/`infra-plan`, label; esistenti con blocchi `import`), stato su HCP Terraform Free in execution mode locale, workflow `infra.yml` con plan nella PR, apply dopo approvazione e deriva il lunedì (issue #76, ADR-0012); B) Terraform per Databricks (issue #78): `infra/databricks/` con cataloghi (creati in SQL da `crea_catalogo.py`), schemi, grant e secret scope, usciti dal bundle con `bundle deployment unbind`; `infra/databricks-identita/` (solo dal PC) con il service principal `academy-terraform` del workflow e i suoi secret negli environment.

Fase 10 (rilascio continuo, issue #81), in due PR: A) pipeline (issue #82): `rilascio.yml` su ogni push a `main` (CI richiamata, un artifact `build/app`, collaudo, fumo, approvazione nell'environment `prod`, produzione, fumo) con il service principal `academy-rilascio` (ADR-0013); B1) feature flag per ambiente dal bundle, spenta per difetto e 404 da spenta, esposta in `/configurazione` (prima flag: evento `.ics` di un'iscrizione Confermata, `ACADEMY_FLAG_CALENDARIO`) e dati di prova sintetici del collaudo caricati all'avvio (`ACADEMY_DATI_PROVA`, vietati in produzione), ADR-0014 (issue #86); B2) rollback e metriche DORA (issue #88, ADR-0015): `rollback.yml` (`workflow_dispatch` con l'id di una run di `rilascio.yml` arrivata in prod: stesso artifact, `databricks.yml` e fumo del suo commit, collaudo poi approvazione di prod) e `scripts/dora.py` (frequenza, lead time, change failure rate, tempo di ripristino dai deployment degli environment di GitHub; metodo e istantanea in `docs/dora.md`).

## Infrastruttura

Terraform per la piattaforma, bundle per il progetto (ADR-0012). Istruzioni e bootstrap in `infra/README.md`. Dal PC: `terraform login` una volta, poi in `infra/github/` `terraform init` e `GITHUB_TOKEN=$(gh auth token) terraform plan`; in `infra/databricks/` e `infra/databricks-identita/` anche `DATABRICKS_CONFIG_PROFILE=academy`. `infra/databricks-identita/` non ha workflow: si applica solo dal PC. Il workflow dell'infrastruttura non è un check obbligatorio (parte solo se cambia `infra/`).

## Databricks

Il bundle (`databricks.yml`) lo rilascia il workflow `rilascio.yml` come service principal `academy-rilascio` (ADR-0013): un merge su `main` va in collaudo, e in produzione dopo l'approvazione nell'environment `prod`. Lo stato del bundle sta nella cartella del service principal: **mai `bundle deploy` con il profilo `academy`**, creerebbe un secondo stato. In emergenza dal PC, con le credenziali del service principal (`infra/README.md`, bootstrap 6):

```bash
python scripts/prepara_app.py   # build/app: pacchetto Python, frontend, requirements.txt con hash, RILASCIO (SHA)
export BUNDLE_VAR_rilascio=$(cat build/app/RILASCIO)   # e BUNDLE_VAR_admin_email
databricks bundle deploy -t collaudo
databricks bundle run academy_hub -t collaudo   # avvia la versione caricata (anche run vuole le variabili)
python scripts/fumo_rilascio.py --app academy-hub-collaudo --ambiente collaudo --rilascio $BUNDLE_VAR_rilascio
```

Rollback (ADR-0015): Actions → Rollback → Run workflow con l'id della run di "Rilascio" da ripristinare (`gh workflow run rollback.yml -f run_id=<id>`), poi approvazione di prod; per tornare avanti, un altro rollback con la run più recente. Metriche DORA: `python scripts/dora.py` (token da `gh auth token`), `--aggiorna docs/dora.md` per l'istantanea.

Con il profilo `academy` restano le letture fuori dal bundle (`databricks apps get`) e l'apertura dell'App nel browser; `bundle summary` va fatto con le credenziali del service principal (con il profilo dell'utente legge la sua cartella, che non c'è più).

Unity Catalog (ADR-0011, ADR-0012): cataloghi, schemi e grant li gestisce Terraform in `infra/databricks/`, non il bundle. La tabella gold sintetica con `uv run --project backend python scripts/unity_catalog.py dati-gold -t <target>`.

## Ambiente locale

Dalla radice del repository, senza altri passaggi (il `.env` è facoltativo, vedi `.env.example`):

```bash
docker compose up -d --build --wait   # db, migrazioni, demo, keycloak, otel-lgtm, backend (+ frontend), job
python scripts/fumo_identita.py       # token veri da Keycloak e flusso richiesta -> approvazione -> conferma
docker compose down                   # -v per cancellare anche i dati
```

L'app completa è su http://localhost:8000 (usa `localhost`, non `127.0.0.1`: è l'origine registrata in Keycloak): l'immagine del backend contiene la build del frontend, quindi dopo una modifica al frontend serve `--build`. Frontend in sviluppo (Node 24, in `frontend/`): `npm ci`, poi `npm run dev` su http://localhost:5173 con il backend di compose dietro il proxy di Vite; si entra con un utente di prova di Keycloak.

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
uv run python -m academy_hub.db.dati_prova    # dati di prova sintetici del collaudo (@academy.example), mai in produzione
uv run python -m academy_hub.contratto        # rigenera backend/contratto/ dopo un cambio dell'API (aumenta VERSIONE_API)
uv run ruff check --fix      # lint
uv run ruff format           # formattazione
uv run pyright               # controllo dei tipi (strict)
uv run pre-commit install    # una volta per clone: hook pre-commit (ruff, gitleaks, ...)
uv run pre-commit run --all-files
```

Dopo ogni modifica a un file `.py` del backend l'hook `.claude/hooks/dopo_modifica.py` lancia ruff e i test veloci (non quelli `integrazione`); se fallisce, correggi prima di proseguire. Prima della PR lancia anche `uv run pytest` completo.

Dentro `frontend/`:

```bash
npm ci                       # dipendenze esatte da package-lock.json
npm run dev                  # Vite su :5173, /api verso 127.0.0.1:8000
npm run api:genera           # rigenera src/api/schema.d.ts dal contratto (dopo academy_hub.contratto)
npm run lint                 # ESLint (typescript-eslint strict, hook di React)
npm run formato              # Prettier in verifica (npm run formatta per correggere)
npm run tipi                 # tsc
npm test                     # Vitest + Testing Library + MSW
npm run build                # build statica in dist/
npx playwright install chromium   # una volta: il browser degli end-to-end
npm run e2e                  # Playwright + axe su docker compose acceso (http://localhost:8000)
```

## Architettura

- `backend/src/academy_hub/`: pacchetto Python. Livelli: router (FastAPI) → servizi (regole di business, autorizzazione) → repository (accesso ai dati). Niente regole nelle rotte, niente SQL fuori dai repository.
  - `api/`: rotte FastAPI (`rotte/`), schemi Pydantic, errori RFC 9457, dipendenze (transazione per richiesta, attore, `If-Match`), provider d'identità (`identita.py`: oidc, databricks, provvisoria; scelto da `ACADEMY_IDENTITA`). `VERSIONE_API` in `api/__init__.py`.
  - `dominio/`: stati dell'iscrizione e transizioni (R7), ruoli, attore, errori di dominio con il loro `tipo`, calendario di Roma; Python puro, senza database.
  - `db/`: modelli SQLAlchemy (`modelli.py`) e migrazioni Alembic (`schema/versions/`). Lo schema cambia solo con una migrazione. Vedi `docs/database.md`.
  - `repository/`: le query, con i lock `FOR UPDATE`. Ordine dei lock: prima l'edizione, poi le sue iscrizioni (ADR-0004).
  - `servizi/`: le regole. Ogni cambio di stato di un'iscrizione passa da un solo punto che verifica la transizione e scrive l'audit (R6). Ogni posto liberato passa da `promuovi_dalla_lista` nella stessa transazione (R4).
  - `db/motore.py`: `crea_motore`, l'unico modo di creare un motore SQLAlchemy (token OAuth come password su Lakebase, `search_path` sullo schema dedicato). `avvio.py`: comando dell'App su Databricks (migrazioni, `db/amministratore.py`, `db/dati_prova.py` se `ACADEMY_DATI_PROVA`, uvicorn).
  - Feature flag (ADR-0014): `ACADEMY_FLAG_<NOME>` in `config.py`, valore per target in `databricks.yml` (collaudo accesa, prod spenta; accesa in `docker-compose.yml`), rotta con la dipendenza che risponde 404 da spenta, campo `flag` di `/configurazione` letto dal frontend (`frontend/src/api/flag.ts`). Una flag si toglie quando la funzione è stabile.
  - `job.py`: job di sistema (scadenza all'inizio dell'edizione, rete di sicurezza della promozione), una transazione per edizione (ADR-0007).
  - `report.py`: porta `LettoreReport` per i report da Unity Catalog, letti con il token dell'utente via Statement Execution API (ADR-0011); `NessunReport` senza warehouse. Adapter verso un sistema esterno, fuori dai livelli: niente regole di business, query fissa, autorizza Unity Catalog.
  - `frontend.py`: serve la build del frontend (`ACADEMY_FRONTEND_DIR`) con fallback su `index.html` per le rotte del client; `/api` resta JSON (ADR-0009 §14).
- `backend/contratto/`: contratto OpenAPI e impronte per versione; `tests/test_contratto.py` fallisce se l'API cambia senza aumentare la versione.
- `backend/tests/`: test pytest. I test HTTP usano la fixture `client` (TestClient sull'app collegata al database di test, identità provvisoria `X-Persona-Id`) e `tests/api.py`; i test del token usano `tests/oidc.py` (chiave RSA di test). `dati.py` crea dati sintetici; `conftest.py` avvia PostgreSQL con la stessa immagine di docker compose e applica le migrazioni.
- `frontend/src/`: `api/` (client `openapi-fetch` tipizzato da `schema.d.ts` generato, `ErroreApi` RFC 9457, hook React Query in `query.ts`), `accesso/` (OIDC o Databricks, secondo `GET /api/v1/configurazione`), `componenti/` (struttura con menu per profilo, stati di caricamento/errore/vuoto, notifiche degli esiti, paginazione), `pagine/` (catalogo, mie iscrizioni, approvazioni; `gestione/` con corsi, edizioni del corso e iscrizioni dell'edizione, hook in `api/gestione.ts`), `test/` (MSW e render con i provider). I test stanno accanto ai file (`*.test.tsx`). `frontend/e2e/`: Playwright su docker compose (`flusso.spec.ts` richiesta → approvazione → conferma, `accessibilita.spec.ts` axe per profilo; `sessione.ts` fa il login su Keycloak e crea con l'API un corso e un'edizione per test).
- `backend/Dockerfile`: multi-stage con uv e uno stage Node che compila il frontend (contesto con nome `frontend`: `docker build --build-context frontend=../frontend backend`), runtime non root (uid 10001).
- `.github/workflows/`: `ci.yml` (lint, typecheck, test, dipendenze con pip-audit su `uv.lock`, frontend, immagine + Trivy, compose, e2e con Playwright e axe, gitleaks), `codeql.yml` (CodeQL su Python, JavaScript/TypeScript e Actions) e `pr-issue.yml` (la PR deve collegare una issue). Sono status check obbligatori del ruleset su `main`. `infra.yml`: Terraform (plan nella PR, apply nell'environment `infra`, deriva), non obbligatorio. `rilascio.yml` (su push a `main`): richiama `ci.yml`, poi `rilascia-ambiente.yml` per collaudo e prod (ADR-0013). `rollback.yml` (a mano, input `run_id`): rilascia di nuovo l'artifact di una run precedente con lo stesso `rilascia-ambiente.yml` (ADR-0015). Sul repository sono attivi secret scanning con push protection, avvisi e aggiornamenti di sicurezza di Dependabot.

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
