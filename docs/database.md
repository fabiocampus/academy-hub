# Database transazionale

PostgreSQL 17: in Docker in locale, Lakebase su Databricks (ADR-0001). Lo schema cambia solo con le migrazioni Alembic in `backend/src/academy_hub/db/schema/versions/`; i modelli SQLAlchemy sono in `backend/src/academy_hub/db/modelli.py`.

## Migrazioni

```bash
# servizio `migrazioni` di docker compose: parte da solo prima del backend
docker compose up -d --wait

# da backend/, contro il PostgreSQL locale (o ACADEMY_DATABASE_URL)
uv run python -m academy_hub.db.migrazioni           # upgrade head
uv run alembic revision --autogenerate -m "..."      # nuova migrazione: rileggila sempre
uv run alembic check                                 # modelli e migrazioni allineati?
```

`test_migrazioni.py` esegue `upgrade head`, `alembic check`, `downgrade base` e di nuovo `upgrade head` su un database vuoto. Autogenerate non vede trigger e funzioni: vanno scritti a mano nella migrazione, con il loro `downgrade`.

I test svuotano le tabelle con `SET LOCAL session_replication_role = replica`, che spegne i trigger solo in quella transazione: in un database vero l'audit non si svuota.

## Tabelle

| Tabella | Contenuto | Vincoli principali |
|---|---|---|
| `team` | Gerarchia dei team (`team_padre_id`) e responsabile | nome unico; un team non è padre di se stesso |
| `persone` | Nome, email, team, ruoli applicativi | email unica; `ruoli` non vuoto e solo fra i codici di `CONTEXT.md` |
| `corsi` | Titolo, descrizione, durata in ore | durata > 0 |
| `edizioni` | Date, capienza, docente, `posti_confermati`, `cancellata_il` | capienza > 0; fine ≥ inizio; `posti_confermati` fra 0 e capienza (R3) |
| `iscrizioni` | Persona, edizione, stato, momenti di richiesta e approvazione | stato fra quelli del glossario; `UNIQUE` parziale sulle attive (R1); data di approvazione obbligatoria dopo l'approvazione |
| `eventi_audit` | Chi, quando, stato di partenza e di arrivo, motivo | solo aggiunta: i trigger rifiutano `UPDATE`, `DELETE` e `TRUNCATE` (R6); `autore_id` nullo = sistema |

Le edizioni non si cancellano: `cancellata_il` le ritira dal catalogo (D10). Gli stati sono testo con un `CHECK`, non un tipo `ENUM` di PostgreSQL: aggiungere uno stato è una migrazione che cambia un vincolo, senza `ALTER TYPE`.

La concorrenza sull'ultimo posto è descritta in [ADR-0004](adr/0004-concorrenza-sull-ultimo-posto.md).

## Indici e piani di esecuzione

Indici sulle ricerche frequenti previste dal backlog:

| Ricerca | Indice |
|---|---|
| Catalogo: edizioni future non cancellate (US-03) | `ix_edizioni_catalogo` su `data_inizio` `WHERE cancellata_il IS NULL` |
| Le mie iscrizioni (US-05) | `ix_iscrizioni_persona_id` |
| Primo in lista d'attesa (US-09, R4) | `ix_iscrizioni_lista_attesa` su (`edizione_id`, `approvata_il`, `id`) `WHERE stato = 'InAttesa'`; `id` fa da spareggio a parità di momento di approvazione |
| Iscrizioni di un'edizione per stato | `ix_iscrizioni_edizione_stato` |
| Audit di un'iscrizione (US-11) | `ix_eventi_audit_iscrizione` su (`iscrizione_id`, `avvenuto_il`) |

`backend/sql/analisi_indici.sql` riempie il database locale con dati sintetici (5 000 persone, 1 000 edizioni, 50 000 iscrizioni, circa 93 000 eventi di audit) ed esegue `EXPLAIN ANALYZE` sulle ricerche. Risultati del 2026-11-14:

| Ricerca | Piano | Tempo |
|---|---|---|
| Catalogo | Index Scan su `ix_edizioni_catalogo`, già ordinato: niente sort | 0,05 ms |
| Le mie iscrizioni | Bitmap Index Scan su `ix_iscrizioni_persona_id` | 0,6 ms |
| Primo in lista d'attesa | Index Scan su `ix_iscrizioni_lista_attesa`, si ferma alla prima riga | 0,09 ms |
| Audit di un'iscrizione | Index Scan su `ix_eventi_audit_iscrizione` | 0,2 ms |

Indici ancora assenti, da valutare con le ricerche della fase 5: `edizioni.docente_id` e `eventi_audit.autore_id`.

Il caso istruttivo è la lista d'attesa. Togliendo i due indici su `edizione_id`, PostgreSQL ripiega sull'indice parziale `uq_iscrizioni_attiva`: legge tutte le 29 iscrizioni attive dell'edizione, ne scarta 23 con un filtro e le ordina. Il tempo sale a circa 1 ms, dieci volte tanto. L'indice parziale con `approvata_il` restituisce invece la prima riga già in ordine.
