# Academy Hub

Prototipo di studio: un'applicazione interna per l'Academy di un'azienda immaginaria. I dipendenti si iscrivono ai corsi, il responsabile approva, l'Academy conferma i posti e gestisce la lista d'attesa; presenze e valutazioni arrivano da file CSV su Databricks, dove vengono controllate e trasformate in report che ogni responsabile vede solo per il proprio team.

> Tutti i dati sono sintetici. Il progetto usa solo piani gratuiti: GitHub Free, Databricks Free Edition, HCP Terraform Free, strumenti open source in locale.

## Che cosa c'è dentro

| Parte | Tecnologie | Cartella |
|---|---|---|
| API e regole di business | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17 / Lakebase | `backend/` |
| Interfaccia web | React, TypeScript, Vite, Mantine, React Query, client generato dal contratto OpenAPI | `frontend/` |
| Parte analitica | PySpark, Lakeflow (SCD 2, Auto Loader), Unity Catalog, controlli di qualità bloccanti | `analisi/` |
| Identità | OIDC con Keycloak in locale, proxy di Databricks Apps in cloud | `keycloak/`, `backend/src/academy_hub/api/identita.py` |
| Infrastruttura | Terraform (GitHub, Unity Catalog, grant, service principal) | `infra/` |
| Rilascio | GitHub Actions, Databricks Asset Bundle, collaudo → approvazione → produzione, rollback | `.github/workflows/`, `databricks.yml` |

Come stanno insieme: [docs/architettura.md](docs/architettura.md) (diagrammi C4).

## Avvio in locale

Serve solo **Docker** (Docker Desktop o equivalente, con Compose v2). Dalla radice del repository:

```bash
docker compose up -d --build --wait   # database, migrazioni, dati demo, Keycloak, backend con il frontend, job
```

La prima volta scarica le immagini e compila: qualche minuto. Poi:

- applicazione: <http://localhost:8000> (usa `localhost`, non `127.0.0.1`: è l'origine registrata in Keycloak);
- documentazione dell'API: <http://localhost:8000/docs>;
- console di Keycloak: <http://localhost:8080> (admin/admin).

Utenti di prova (password uguale al nome): `dipendente`, `responsabile`, `dirigente`, `admin` (amministratore Academy), `docente`, `esterna` (non registrata nell'Academy: vede l'errore 403).

Un giro completo: entra come `dipendente` e chiedi l'iscrizione a un'edizione del catalogo; entra come `responsabile` e approvala in *Approvazioni*; entra come `admin` e conferma il posto in *Gestione*. Lo stesso flusso, senza browser:

```bash
python scripts/fumo_identita.py
```

Per fermare: `docker compose down` (`-v` cancella anche i dati). Il file `.env` è facoltativo (vedi `.env.example`).

## Sviluppo

Strumenti: [uv](https://docs.astral.sh/uv/) (Python), Node 24 con npm, Docker per i test d'integrazione. In alternativa c'è il dev container (`.devcontainer/`).

```bash
cd backend && uv sync && uv run pytest        # test (quelli `integrazione` avviano PostgreSQL con Testcontainers)
cd frontend && npm ci && npm test             # Vitest; npm run dev per il server di sviluppo su :5173
cd analisi && uv sync && uv run pytest        # trasformazioni su Spark locale (serve Java 17+)
```

Tutti i comandi, la struttura del codice e le regole sono in [CLAUDE.md](CLAUDE.md) (scritto per l'agente, utile a chiunque). Come proporre una modifica: [CONTRIBUTING.md](CONTRIBUTING.md).

## In cloud

Ogni merge su `main` passa la CI, va in **collaudo** su Databricks Apps con un test di fumo e, dopo un'approvazione, in **produzione** (ADR-0013). Un rollback rilascia di nuovo l'artifact di una run precedente (ADR-0015). Il job `analisi` gira ogni giorno: snapshot del database transazionale, storico SCD 2, importazione e controllo dei CSV, report gold riscritti solo se nessun file è stato respinto (ADR-0016, ADR-0017). Che cosa fare quando qualcosa si rompe: [docs/runbook.md](docs/runbook.md).

## Documentazione

- [Visione del prodotto](docs/visione.md) e [backlog iniziale](docs/backlog.md)
- [Glossario del dominio](CONTEXT.md)
- [Architettura](docs/architettura.md) e [Architecture Decision Record](docs/adr/)
- [Processo di lavoro: Definition of Ready e Definition of Done](docs/processo.md)
- [Database e indici](docs/database.md)
- [Threat model](docs/threat-model.md)
- [SLI e SLO](docs/slo.md), [runbook](docs/runbook.md), [post-mortem](docs/postmortem/)
- [Metriche DORA](docs/dora.md)
- [Retrospettiva dello sviluppo con un agente](docs/retrospettiva-ai.md)
- [Infrastruttura e bootstrap](infra/README.md)
- [CSV di esempio](data/samples/README.md)

## Stato

Prototipo completo nelle fasi 1–13 del piano di studio. Rimandati: synced table verso Lakebase, pagina dei report nel frontend (i report sono già nell'API), tracce OpenTelemetry.
