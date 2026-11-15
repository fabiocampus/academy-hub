# ADR-0011 · Unity Catalog e le due identità dell'App

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Fase 8, seconda parte: la parte analitica vive in Unity Catalog, un catalogo per ambiente con i livelli `bronze`, `silver`, `gold`. L'App (ADR-0010) gira con il suo service principal, che possiede lo schema Lakebase e scrive le iscrizioni. I report invece vanno letti rispettando i permessi di chi li chiede: se l'App li leggesse con il suo service principal, a decidere chi vede che cosa sarebbe il codice dell'App, non Unity Catalog.

Databricks Apps può passare all'App il token dell'utente collegato (on-behalf-of-user): con gli scope dichiarati in `user_api_scopes`, il proxy mette in `X-Forwarded-Access-Token` un token dell'utente limitato a quegli scope.

Scoperte su Free Edition:

- Il metastore non ha uno storage root: l'API dei cataloghi (e quindi la risorsa `catalogs` del bundle) rifiuta di crearli con «Metastore storage root URL does not exist». `CREATE CATALOG` in SQL invece li crea sul Default Storage.
- Un solo utente nel workspace, che è anche proprietario dei cataloghi: un rifiuto vero di Unity Catalog con il token di un altro utente qui non si può provare.
- Costruire un client dell'SDK risolve la configurazione in rete (circa un secondo, misurato): troppo per farlo a ogni richiesta con un token diverso.
- In Spark SQL `''` dentro una stringa non è un apice: sono due stringhe concatenate.

## Decisione

1. **Un catalogo per target**: `academy_collaudo` e `academy_prod`, con gli schemi `bronze`, `silver`, `gold`. Dalla fase 9 cataloghi, schemi e grant li gestisce Terraform in `infra/databricks` (ADR-0012 §7), che crea il catalogo in SQL; il bundle passa all'App solo il nome del catalogo (`var.catalogo`). Nella fase 8 stavano nel bundle, con il catalogo creato da uno script e preso in carico con `bundle deployment bind`.
2. **Grant minimi, solo agli utenti**: `account users` ha `USE CATALOG` sul catalogo e `USE SCHEMA`, `SELECT` su `gold`; `bronze` e `silver` restano al proprietario. Il service principal dell'App non ha grant su Unity Catalog.
3. **Due identità, due usi**: il service principal per Lakebase (tutto il transazionale, ADR-0010); il token dell'utente solo per le query dei report, con lo scope `sql` e la risorsa `sql_warehouse` dell'App (`CAN_USE`), da cui l'App riceve l'id del warehouse (`value_from`). Il bundle trova il warehouse per nome (`lookup`): l'id è del workspace e non sta nel repository.
4. **Porta `LettoreReport`** (`academy_hub/report.py`): l'adapter Databricks manda la query alla Statement Execution API con il token dell'utente come Bearer, con una sessione HTTP riusata (che non accetta cookie, perché è condivisa fra gli utenti) e senza SDK per richiesta. Catalogo e schema sono parametri della richiesta, mai nel testo SQL. Attesa 30 secondi, poi la query si annulla (`on_wait_timeout: CANCEL`). Senza warehouse configurato il lettore è `NessunReport` (locale, test). È un adapter verso un sistema esterno e sta fuori dai livelli router → servizi → repository: non ha regole di business, la sua unica query è fissa e l'autorizzazione la fa Unity Catalog; la rotta lo chiama direttamente.
5. **Errori**: Unity Catalog che nega (`PERMISSION_DENIED`, `INSUFFICIENT_PERMISSIONS`) o il warehouse negato (HTTP 403) → 403 `report-non-autorizzato`; tutto il resto → 503 `report-non-disponibile`: token assente, token rifiutato a valle (HTTP 401: l'utente è autenticato presso l'App, un 401 farebbe solo rifare il login), tabella mancante, colonne inattese, warehouse che non risponde in tempo. Al client arrivano messaggi generici (D10); stato HTTP, codice e classe d'errore di Databricks vanno solo nel log, il token mai.
6. **Rotta `GET /api/v1/report/iscrizioni-per-corso`** (contratto 1.6.0): basta essere una persona registrata; chi legge la tabella lo decide Unity Catalog. La risposta riporta `letto_come` (`current_user()` della query) e ha `Cache-Control: no-store`, perché dipende da chi chiede.
7. **Dati gold sintetici** fino alla fase 11: `scripts/unity_catalog.py dati-gold` ricrea `gold.iscrizioni_per_corso` con valori fissi.

## Conseguenze

- I permessi sui report si gestiscono in Unity Catalog, non nel codice: togliere `SELECT` a un gruppo basta a chiudergli il report.
- Il catalogo non nasce dal `bundle deploy`: prima serve l'`apply` di `infra/databricks`. Distruggere il bundle non tocca più cataloghi e schemi.
- Una query su un warehouse serverless spento aspetta che parta (qualche secondo in collaudo); oltre 30 secondi il report risponde 503 e si riprova.
- Il rifiuto di Unity Catalog è provato con le risposte della Statement Execution API nei test; sul workspace si è verificato che la query gira come l'utente (`letto_come`), non come il service principal.
- Lo scope `sql` del token passato all'App vale per qualunque query SQL dell'utente: l'App ne fa solo una, fissa. Il token resta in memoria per la durata della richiesta.
