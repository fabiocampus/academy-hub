# Academy Hub

Prototipo di studio: iscrizioni ai corsi di un'Academy aziendale (parte transazionale) e report con controlli di qualità su Databricks (parte analitica). Leggi `docs/visione.md` e `CONTEXT.md` prima di lavorare sul dominio.

## Stato

Fasi 1–12 del piano chiuse, fase 13 (documentazione) in corso: la storia per fase è nelle issue epic (#49 API, #36/#56 sicurezza, #59 frontend, #68 Databricks, #75 infrastruttura, #81 rilascio, #91 analisi, #107 osservabilità) e negli ADR. Mappa del sistema in `docs/architettura.md` (C4 in Mermaid), avvio in `README.md`, regole di contribuzione in `CONTRIBUTING.md`, errori dell'agente e regole nate da essi in `docs/retrospettiva-ai.md`. Rimandati: synced table e pagina dei report nel frontend (fase 11), OpenTelemetry (fase 12).

## Strumenti dell'agente

- **GitHub con `gh`**, non con il server MCP di GitHub (ADR-0019): `gh issue view <n> --comments`, `gh pr view/checks`, `gh run view`, `gh api` per sub-issue e board. Su questo PC la rete verso api.github.com a volte cade: ripeti la chiamata.
- **Skill di progetto** in `.claude/skills/`: `nuova-migrazione` (Alembic, expand/contract) e `nuova-rotta` (test, matrice di autorizzazione, contratto, client del frontend). Seguile invece di improvvisare i passi.
- **Subagent `revisore`** (`.claude/agents/revisore.md`) prima di ogni merge. Se la sessione è partita fuori da `academy-hub/` non è caricato: usa un agente generico con quelle istruzioni.
- **Hook** `.claude/hooks/dopo_modifica.py` dopo ogni modifica a un `.py` del backend.

## Lezioni imparate

Errori già fatti, da non ripetere:

- **Databricks serverless**: un `spark_python_task` gira in IPython, quindi qualsiasi `SystemExit` (anche 0) fa fallire il task (#97); nella pipeline Lakeflow `spark.catalog.tableExists` e `getCondition()` non sono ammessi (#101); un job con un task finale `ALL_DONE` finisce `SUCCESS_WITH_FAILURES` e non fa scattare `on_failure` del job: le email vanno sui task (post-mortem 2026-11-15); i task falliti vengono ritentati in automatico nella stessa run.
- **Unity Catalog**: il proprietario di un catalogo non ha `SELECT` sulle tabelle figlie senza grant; gli schemi di Lakebase registrati in UC non si vedono dall'API dei grant finché una query SQL non li legge (`carica_schemi.py`). Uno schema nominato dal bundle deve esistere in Terraform (`test_bundle_schemi.py`).
- **Bundle**: mai `bundle deploy` con il profilo `academy`; una cache `.databricks/` locale vince sullo stato remoto; i bind vogliono chiavi qualificate (`apps.academy_hub`); `bundle run` vuole le stesse `BUNDLE_VAR_*` del deploy.
- **Rilascio**: un push su `main` che cambia `infra/` fa partire insieme Rilascio e apply dell'infrastruttura: il job `analisi` non va lanciato prima dell'apply. Modificare il corpo di una PR rilancia `issue-collegata`: aspetta prima del merge.
- **Windows**: leggi e scrivi i file con `encoding="utf-8"` (e `newline="\n"`); in Git Bash `MSYS_NO_PATHCONV=1` per i percorsi del workspace; per gli script dal PC verso PostgreSQL di compose usa `127.0.0.1`, per il browser `localhost`; Spark locale su Windows non legge file (quelle prove girano solo in CI).
- **Test**: un test deve verificare stato **e** effetto (corpo della risposta, righe nel database), non solo che il codice non esploda; le rotte dietro una flag spenta rispondono 404, quindi i test su tutte le rotte vogliono le flag accese; una dipendenza nuova si verifica sul registro (PyPI, npm) prima di aggiungerla, con la versione esatta nel lock.

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

Rollback (ADR-0015): Actions → Rollback → Run workflow con l'id della run di "Rilascio" da ripristinare (`gh workflow run rollback.yml -f run_id=<id>`), poi approvazione di prod; prima rifiuta i prod di `rilascio.yml` in attesa e non fare merge finché il rollback non finisce (stesso gruppo di concurrency); per tornare avanti, un altro rollback con la run più recente. Metriche DORA: `python scripts/dora.py` (token da `gh auth token`), `--aggiorna docs/dora.md` per l'istantanea.

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

Dentro `analisi/` (Python 3.12, come l'ambiente serverless 4 di Databricks; i test avviano Spark in locale: serve Java 17, non 24+ per Hadoop):

```bash
uv sync                      # pyspark e gli strumenti, solo per sviluppo e test
uv run pytest                # trasformazioni su Spark locale
uv run ruff check --fix && uv run ruff format
uv run pyright               # strict
```

Il job gira solo su Databricks (`databricks bundle run analisi -t collaudo`, come service principal e con le stesse variabili `BUNDLE_VAR_*` di `bundle run academy_hub`): `create_auto_cdc_from_snapshot_flow` non esiste in pyspark open source.

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
  - `osservabilita.py`: log JSON su una riga (`configura_log`, anche per uvicorn, senza access log) e middleware `Correlazione` (`X-Request-Id` letto o generato, restituito, una riga per richiesta con la rotta e non il percorso). Nei log niente dati personali né segreti: le eccezioni escono con classe e stack, senza messaggio (fase 12).
  - `frontend.py`: serve la build del frontend (`ACADEMY_FRONTEND_DIR`) con fallback su `index.html` per le rotte del client; `/api` resta JSON (ADR-0009 §14).
- `analisi/src/`: job e pipeline della parte analitica (ADR-0016). `academy_analisi/tabelle.py` elenca tabelle e colonne copiate da Lakebase (mai `SELECT *`; `backend/tests/test_contratto_analisi.py` le lega al modello SQLAlchemy: togliere o rinominare una colonna letta richiede di aggiornarle), `snapshot.py` lo scatto in `bronze`, `storico.py` la sorgente dello SCD 2, `importazioni.py` la lettura dei CSV con Auto Loader, `qualita.py` le regole e la quarantena, `gate.py` verdetti ed esito, `gold.py` i report (ADR-0017), `letture.py` le letture di tabelle che possono mancare. I punti d'ingresso su Databricks (`snapshot_bronze.py`, `controlli_qualita.py`, `aggiorna_gold.py`, `registra_esito.py`, le librerie della pipeline `pipeline_storico.py` e `pipeline_importazioni.py`) restano sottili e sono copiati da `scripts/prepara_app.py` in `build/app/analisi/`; un test del backend controlla che i file nominati da `databricks.yml` ci siano. Mai `spark.catalog.tableExists` né `getCondition()` nella pipeline serverless (#101). Le prove di lettura di file con Spark girano solo su Linux (CI).
- `backend/contratto/`: contratto OpenAPI e impronte per versione; `tests/test_contratto.py` fallisce se l'API cambia senza aumentare la versione.
- `backend/tests/`: test pytest. I test HTTP usano la fixture `client` (TestClient sull'app collegata al database di test, identità provvisoria `X-Persona-Id`) e `tests/api.py`; i test del token usano `tests/oidc.py` (chiave RSA di test). `dati.py` crea dati sintetici; `conftest.py` avvia PostgreSQL con la stessa immagine di docker compose e applica le migrazioni.
- `frontend/src/`: `api/` (client `openapi-fetch` tipizzato da `schema.d.ts` generato, `ErroreApi` RFC 9457, hook React Query in `query.ts`), `accesso/` (OIDC o Databricks, secondo `GET /api/v1/configurazione`), `componenti/` (struttura con menu per profilo, stati di caricamento/errore/vuoto, notifiche degli esiti, paginazione), `pagine/` (catalogo, mie iscrizioni, approvazioni; `gestione/` con corsi, edizioni del corso e iscrizioni dell'edizione, hook in `api/gestione.ts`), `test/` (MSW e render con i provider). I test stanno accanto ai file (`*.test.tsx`). `frontend/e2e/`: Playwright su docker compose (`flusso.spec.ts` richiesta → approvazione → conferma, `accessibilita.spec.ts` axe per profilo; `sessione.ts` fa il login su Keycloak e crea con l'API un corso e un'edizione per test).
- `backend/Dockerfile`: multi-stage con uv e uno stage Node che compila il frontend (contesto con nome `frontend`: `docker build --build-context frontend=../frontend backend`), runtime non root (uid 10001).
- `.github/workflows/`: `ci.yml` (lint, typecheck, test, dipendenze con pip-audit su `uv.lock`, analisi, frontend, immagine + Trivy, compose, e2e con Playwright e axe, gitleaks), `codeql.yml` (CodeQL su Python, JavaScript/TypeScript e Actions) e `pr-issue.yml` (la PR deve collegare una issue). Sono status check obbligatori del ruleset su `main`. `infra.yml`: Terraform (plan nella PR, apply nell'environment `infra`, deriva), non obbligatorio. `rilascio.yml` (su push a `main`): richiama `ci.yml`, poi `rilascia-ambiente.yml` per collaudo e prod (ADR-0013). `rollback.yml` (a mano, input `run_id`): rilascia di nuovo l'artifact di una run precedente con lo stesso `rilascia-ambiente.yml` (ADR-0015). Sul repository sono attivi secret scanning con push protection, avvisi e aggiornamenti di sicurezza di Dependabot.

## Flusso di lavoro

1. Issue → branch `<tipo>/<n>-<descrizione>` da `main`.
2. Test prima del codice per i criteri di accettazione.
3. Comandi verdi in locale, poi PR con `Closes #n` e l'elenco di che cosa hai eseguito.
4. Rilettura con il subagent `revisore` (`.claude/agents/revisore.md`) prima del merge (squash).
5. Dopo il merge: Rilascio in collaudo, fumo, approvazione di `prod` da parte dell'utente (mai approvare al suo posto).

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
