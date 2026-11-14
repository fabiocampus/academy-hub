# ADR-0010 · L'App su Databricks: bundle, Lakebase con token OAuth, avvio con le migrazioni

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Fase 8: l'applicazione (API e frontend, ADR-0009 §14) gira come Databricks App su Free Edition e usa Lakebase al posto del PostgreSQL di docker compose. Vincoli di Free Edition: un solo workspace (ADR-0002), un solo progetto Lakebase, fino a 3 App, niente account console. Il repository è pubblico: niente URL del workspace, email reali o credenziali nei file.

Lakebase Autoscaling non ha password statiche per le identità di Databricks: ci si collega con un token OAuth che scade dopo un'ora. Aggiungendo all'App una risorsa `postgres`, la piattaforma crea il ruolo Postgres del service principal dell'App, gli dà `CONNECT` e `CREATE` sul database e inietta le variabili di libpq (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`). Lo schema `public` non è del service principal.

## Decisione

1. **Un Declarative Automation Bundle** (`databricks.yml` nella radice) con i target `collaudo` e `prod`, `mode: production`. Il bundle descrive l'App, la sua risorsa `postgres` e le risorse Lakebase; workspace e credenziali arrivano dal profilo della CLI o dalle variabili d'ambiente, mai dal file. Il deploy si fa da PC in questa fase; la CI lo farà nella fase 10.
2. **Un progetto Lakebase, un branch per ambiente.** Il progetto `academy-hub` (Postgres 17, come ADR-0001) appartiene al target `prod`, con `prevent_destroy`, e il suo branch di difetto `production` è quello di prod. Il target `collaudo` aggiunge il branch `collaudo` con il suo endpoint read-write (0,5–1 CU, sospeso dopo 5 minuti). Il primo deploy è quindi quello di prod. Il confine con Terraform (piattaforma vs risorse del progetto) si decide nella fase 9.
3. **Password = token, generato a ogni nuova connessione.** `db/motore.py` (`crea_motore`) è l'unico punto che crea un motore SQLAlchemy, per app, job, dati iniziali e migrazioni. L'URL su Databricks è `postgresql+psycopg://`: il resto lo legge libpq dalle variabili `PG*`. Con `ACADEMY_LAKEBASE_ENDPOINT` un evento `do_connect` mette come password il token di `generate_database_credential` dell'SDK, con l'identità di chi gira (il service principal dell'App; dal PC l'utente della CLI). Un token per connessione e non uno condiviso: il pool riusa le connessioni aperte, che restano valide dopo la scadenza del token, e se ne apre di nuove solo ogni tanto.
4. **Schema dedicato.** Con `ACADEMY_DATABASE_SCHEMA=academy` le migrazioni creano lo schema se manca e il motore imposta `search_path` a ogni connessione (con `SET`, non con l'opzione di avvio, che i pooler rifiutano). Schema, tabelle e `alembic_version` sono del service principal; le migrazioni non nominano mai lo schema.
5. **Avvio: migrazioni, amministratore, uvicorn.** Il comando dell'App è `python -m academy_hub.avvio`: migrazioni Alembic, poi la persona `admin_academy` di `ACADEMY_ADMIN_EMAIL` se manca, poi uvicorn sulla porta dell'App. L'email arriva dalla variabile `admin_email` del bundle, passata al deploy (`--var`), mai committata. Una persona già presente non si tocca: riavviare non ridà ruoli tolti.
6. **Pacchetto dell'App generato.** `scripts/prepara_app.py` mette in `build/app/` (ignorata da Git) il pacchetto Python, la build del frontend e `requirements.txt` esportato da `uv.lock` con gli hash. Il bundle sincronizza solo quella cartella.
7. **`ACADEMY_AMBIENTE` dichiarato (#58).** Il default resta `locale` per i comandi di sviluppo, ma l'identità `provvisoria` richiede che l'ambiente sia stato impostato esplicitamente.

## Conseguenze

- Più semplice: nessuna password da conservare o ruotare per il database; la stessa immagine logica (pacchetto + frontend) gira in locale e su Databricks, cambia solo la configurazione.
- Le migrazioni all'avvio rallentano la partenza dell'App e girano a ogni riavvio (sono idempotenti). Con più istanze servirebbe un lock; Free Edition ne ha una.
- Il progetto Lakebase dipende dal target `prod`: distruggere prod non lo cancella (`prevent_destroy`), ma il deploy di collaudo da zero richiede prima quello di prod.
- `databricks-sdk` diventa una dipendenza di runtime anche in locale, importata solo con Lakebase.
- I test non possono usare Lakebase: verificano il meccanismo con PostgreSQL e un generatore di token finto; il collegamento vero si prova con il deploy su collaudo.
