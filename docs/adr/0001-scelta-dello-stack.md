# ADR-0001 · Scelta dello stack

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Academy Hub ha una parte transazionale (iscrizioni, approvazioni, posti, audit) e una parte analitica (presenze, valutazioni, report con controlli di qualità). Deve girare in locale con strumenti gratuiti e in collaudo e produzione su Databricks Free Edition, senza modificare il codice fra un ambiente e l'altro. Lo sviluppa una sola persona con Claude Code come assistente.

Vincoli che orientano la scelta:

- Databricks Apps esegue applicazioni Python (o Node.js) e offre Lakebase, un PostgreSQL gestito.
- Free Edition permette poche App per account: conviene un solo processo che serva API e interfaccia.
- Il corso di riferimento insegna Python, API a livelli, React con TypeScript, SQL e Delta.

## Decisione

| Strato | Scelta |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2 con Alembic; architettura router → servizi → repository |
| Gestione del progetto Python | `uv`, `pyproject.toml`, `ruff`, `pyright`, `pytest` |
| Frontend | React con TypeScript e Vite; client generato dal contratto OpenAPI; React Query |
| Database transazionale | PostgreSQL: in Docker in locale, Lakebase su Databricks |
| Parte analitica | Tabelle Delta in Unity Catalog (bronze, silver, gold); Lakeflow Declarative Pipelines con expectations |
| Rilascio | Declarative Automation Bundles per Databricks; GitHub Actions per CI/CD (vedi ADR-0003) |
| Infrastruttura come codice | Terraform con i provider `github` e `databricks` |
| Identità in locale | Keycloak (OIDC) in Docker |
| Osservabilità in locale | OpenTelemetry verso `grafana/otel-lgtm` in Docker |

In produzione la build statica del frontend è servita dallo stesso processo FastAPI: l'intera applicazione è **una sola Databricks App**.

La versione di Python del progetto è allineata a quella dell'ambiente di Databricks Apps. La verifichiamo nella fase 3 e la fissiamo in `.python-version`.

**Verifica (2026-11-14, fase 3).** La pagina *system environment* di Databricks Apps indica Ubuntu 22.04, Python 3.11 e uv 0.13.5; non elenca librerie preinstallate da cui dipendere. Di conseguenza:

- `backend/.python-version` = `3.11`, `requires-python = ">=3.11,<3.12"`, immagine Docker `python:3.11.x-slim`;
- le dipendenze sono fissate in `backend/uv.lock`, che l'App installerà con uv: non usiamo le librerie preinstallate della piattaforma;
- l'App ascolta sulla porta che la piattaforma passa in `UVICORN_PORT`/`UVICORN_HOST` (da `DATABRICKS_APP_PORT`); in locale le stesse variabili le fissa il Dockerfile;
- PostgreSQL locale alla versione 17, la stessa che useremo su Lakebase (da riverificare nella fase 8).

## Conseguenze

- **Positive:** un solo linguaggio lato server per App, job e pipeline; PostgreSQL uguale in locale e su Lakebase; il contratto OpenAPI tiene allineati backend e frontend; lo stack corrisponde ai moduli del corso.
- **Negative:** FastAPI che serve anche i file statici è meno efficiente di un CDN, ma è irrilevante per un prototipo. Le dipendenze Python vanno tenute compatibili con l'ambiente di Databricks Apps.
- **Da rivalutare:** se una funzione di Lakebase usata in produzione non esiste nel PostgreSQL locale, documentiamo la differenza e la isoliamo nel livello repository.

## Alternative considerate

- **Node.js per il backend:** supportato da Databricks Apps, ma separerebbe il linguaggio dell'App da quello di job e pipeline.
- **Streamlit o Dash:** più rapidi da avviare, ma non insegnano API a livelli, contratto OpenAPI né frontend tipizzato.
- **Un database diverso da PostgreSQL in locale (SQLite):** più semplice, ma nasconderebbe proprio i comportamenti da studiare: concorrenza, `SELECT … FOR UPDATE`, vincoli `UNIQUE` parziali.
