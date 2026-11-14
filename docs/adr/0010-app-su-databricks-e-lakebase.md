# ADR-0010 · L'App su Databricks: bundle, Lakebase con token OAuth, avvio con le migrazioni

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Fase 8: l'applicazione (API e frontend, ADR-0009 §14) gira come Databricks App su Free Edition e usa Lakebase al posto del PostgreSQL di docker compose. Vincoli di Free Edition: un solo workspace (ADR-0002), un solo progetto Lakebase, fino a 3 App, niente account console. Il repository è pubblico: niente URL del workspace, email reali o credenziali nei file.

Lakebase Autoscaling non ha password statiche per le identità di Databricks: ci si collega con un token OAuth che scade dopo un'ora. Aggiungendo all'App una risorsa `postgres`, la piattaforma crea il ruolo Postgres del service principal dell'App, gli dà `CONNECT` e `CREATE` sul database e inietta le variabili di libpq (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`). Lo schema `public` non è del service principal.

## Decisione

1. **Un Declarative Automation Bundle** (`databricks.yml` nella radice) con i target `collaudo` e `prod`, `mode: production`. Il bundle descrive l'App, la sua risorsa `postgres` e le risorse Lakebase; workspace e credenziali arrivano dal profilo della CLI o dalle variabili d'ambiente, mai dal file. Il deploy si fa da PC in questa fase; la CI lo farà nella fase 10.
2. **Un progetto Lakebase, un branch per ambiente.** Il progetto `academy-hub` (Postgres 17, come ADR-0001) appartiene al target `prod`, con `prevent_destroy`, e il suo branch di difetto `production` è quello di prod. Il target `collaudo` aggiunge il branch `collaudo`. Ogni branch nasce già con un endpoint read-write (`primary`): il bundle lo prende in carico (`replace_existing`) e lo limita a 0,5–1 CU. La sospensione per inattività resta quella di Free Edition, che non si può cambiare. La risorsa `postgres` dell'App sta nei target e punta all'endpoint con un riferimento `${resources...}`, così il bundle crea Lakebase prima dell'App. Il primo deploy è quello di prod. Il confine con Terraform (piattaforma vs risorse del progetto) si decide nella fase 9.
3. **Password = token, generato a ogni nuova connessione.** `db/motore.py` (`crea_motore`) è l'unico punto che crea un motore SQLAlchemy, per app, job, dati iniziali e migrazioni. L'URL su Databricks è `postgresql+psycopg://`: il resto lo legge libpq dalle variabili `PG*`. Con `ACADEMY_LAKEBASE_ENDPOINT` un evento `do_connect` mette come password il token di `generate_database_credential` dell'SDK, con l'identità di chi gira (il service principal dell'App; dal PC l'utente della CLI). Un token per connessione e non uno condiviso: il pool riusa le connessioni aperte, che restano valide dopo la scadenza del token, e se ne apre di nuove solo ogni tanto.
4. **Uno schema per ambiente.** Con `ACADEMY_DATABASE_SCHEMA` le migrazioni creano lo schema se manca e il motore imposta `search_path` a ogni connessione (con `SET`, non con l'opzione di avvio, che i pooler rifiutano). Schema, tabelle e `alembic_version` sono del service principal dell'App; le migrazioni non nominano mai lo schema. Prod usa `academy`, collaudo `academy_collaudo`: un branch nasce come copia di `production`, quindi contiene anche lo schema `academy` dell'App di prod, che il service principal di collaudo non può usare (senza `USAGE` Postgres lo salta nel `search_path` e la prima `CREATE TABLE` fallisce con «no schema has been selected»).
5. **Avvio: migrazioni, amministratore, uvicorn.** Il comando dell'App è `python -m academy_hub.avvio`: migrazioni Alembic, poi la persona `admin_academy` di `ACADEMY_ADMIN_EMAIL` se manca, poi uvicorn sulla porta dell'App. L'email arriva dalla variabile `admin_email` del bundle, passata al deploy (`--var`), mai committata. Una persona già presente non si tocca: riavviare non ridà ruoli tolti.
6. **Pacchetto dell'App generato.** `scripts/prepara_app.py` mette in `build/app/` (ignorata da Git) il pacchetto Python, la build del frontend e `requirements.txt` esportato da `uv.lock` con gli hash. Il bundle sincronizza solo quella cartella.
7. **`ACADEMY_AMBIENTE` dichiarato (#58).** Il default resta `locale` per i comandi di sviluppo, ma l'identità `provvisoria` richiede che l'ambiente sia stato impostato esplicitamente.

## Conseguenze

- Più semplice: nessuna password da conservare o ruotare per il database; la stessa immagine logica (pacchetto + frontend) gira in locale e su Databricks, cambia solo la configurazione.
- Le migrazioni all'avvio rallentano la partenza dell'App e girano a ogni riavvio (sono idempotenti). Con più istanze servirebbe un lock; Free Edition ne ha una.
- Il progetto Lakebase dipende dal target `prod`: distruggere prod non lo cancella (`prevent_destroy`), ma il deploy di collaudo da zero richiede prima quello di prod.
- `databricks-sdk` diventa una dipendenza di runtime anche in locale, importata solo con Lakebase.
- Il branch di collaudo contiene una copia dei dati di prod del momento in cui è nato, illeggibile dall'App di collaudo ma visibile al proprietario del progetto. Qui i dati sono sintetici; con dati reali servirebbe un branch da uno stato vuoto o mascherato.
- Databricks Apps ha pacchetti preinstallati (Streamlit, Gradio, MLflow): pip segnala conflitti con le versioni di `requirements.txt`, innocui perché l'App non li importa.
- I test non possono usare Lakebase: verificano il meccanismo con PostgreSQL e un generatore di token finto; il collegamento vero si prova con il deploy su collaudo.
