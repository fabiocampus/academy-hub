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
| `corsi` | Titolo, descrizione, durata in ore, `archiviato_il`, `versione` | durata > 0 |
| `edizioni` | Date, capienza, docente, `posti_confermati`, `cancellata_il`, `versione` | capienza > 0; fine ≥ inizio; `posti_confermati` fra 0 e capienza (R3) |
| `iscrizioni` | Persona, edizione, stato, momenti di richiesta e approvazione, chiave di idempotenza | stato fra quelli del glossario; `UNIQUE` parziale sulle attive (R1); data di approvazione obbligatoria dopo l'approvazione; `UNIQUE` parziale su (persona, chiave di idempotenza) (ADR-0006) |
| `eventi_audit` | Chi, quando, stato di partenza e di arrivo, motivo | solo aggiunta: i trigger rifiutano `UPDATE`, `DELETE` e `TRUNCATE` (R6); `autore_id` nullo = sistema |

Le edizioni non si cancellano: `cancellata_il` le ritira dal catalogo (D10). I corsi archiviati (`archiviato_il`) escono dal catalogo con le loro edizioni, che restano per i report (US-01). `versione` è il contatore della concorrenza ottimistica: lo incrementa SQLAlchemy a ogni modifica (`version_id_col`) e l'API lo espone come `ETag` (ADR-0005). Gli stati sono testo con un `CHECK`, non un tipo `ENUM` di PostgreSQL: aggiungere uno stato è una migrazione che cambia un vincolo, senza `ALTER TYPE`.

La concorrenza sull'ultimo posto è descritta in [ADR-0004](adr/0004-concorrenza-sull-ultimo-posto.md), quella delle richieste ripetute in [ADR-0006](adr/0006-idempotenza-della-richiesta.md).

Il responsabile diretto si ricava risalendo `team.team_padre_id` con una CTE ricorsiva (`repository/persone.py:antenati`), limitata a 50 livelli come difesa da una gerarchia ciclica.

## Indici e piani di esecuzione

Indici sulle ricerche frequenti previste dal backlog:

| Ricerca | Indice |
|---|---|
| Catalogo: edizioni future non cancellate (US-03) | `ix_edizioni_catalogo` su `data_inizio` `WHERE cancellata_il IS NULL` |
| Le mie iscrizioni (US-05) | `ix_iscrizioni_persona_id`; la posizione in lista d'attesa con `ix_iscrizioni_lista_attesa` |
| Richieste da decidere (US-07) | `ix_persone_team_id` per le persone dei team, poi `uq_iscrizioni_attiva` per le loro iscrizioni |
| Primo in lista d'attesa (US-09, R4) | `ix_iscrizioni_lista_attesa` su (`edizione_id`, `approvata_il`, `id`) `WHERE stato = 'InAttesa'`; `id` fa da spareggio a parità di momento di approvazione |
| Iscrizioni di un'edizione per stato | `ix_iscrizioni_edizione_stato` |
| Audit di un'iscrizione (US-11) | `ix_eventi_audit_iscrizione` su (`iscrizione_id`, `avvenuto_il`) |
| Ripetizione di una richiesta (US-04) | `uq_iscrizioni_chiave_idempotenza` su (`persona_id`, `chiave_idempotenza`) `WHERE chiave_idempotenza IS NOT NULL` |
| Job: edizioni iniziate con iscrizioni pendenti (US-17) | scansione delle edizioni (vedi sotto), poi `ix_iscrizioni_edizione_stato` per l'esistenza delle pendenti |
| Job: edizioni aperte con posti liberi e lista d'attesa (US-09) | scansione delle edizioni (vedi sotto), poi `ix_iscrizioni_lista_attesa` |
| Iscrizioni attive di un'edizione da annullare (US-17, US-18) | `ix_iscrizioni_edizione_stato` |

`backend/sql/analisi_indici.sql` riempie il database locale con dati sintetici (50 team su tre livelli, 5 000 persone, 1 000 edizioni, 50 000 iscrizioni, circa 93 000 eventi di audit) ed esegue `EXPLAIN ANALYZE` sulle ricerche. Per l'API e il job usa l'SQL che generano i repository, catturato dal driver. Risultati del 2026-11-14:

| Ricerca | Piano | Tempo |
|---|---|---|
| Catalogo | Index Scan su `ix_edizioni_catalogo`, già ordinato: niente sort | 0,05 ms |
| Le mie iscrizioni (US-05), conteggio e pagina | Bitmap Index Scan su `ix_iscrizioni_persona_id`; posizione in lista con `ix_iscrizioni_lista_attesa` | 0,2 ms + 1 ms |
| Richieste da decidere (US-07), conteggio e pagina | `DISTINCT ON` sulla catena dei responsabili, poi `uq_iscrizioni_attiva` per persona | 10-18 ms ciascuna |
| Job: edizioni iniziate con pendenti (US-17) | Seq Scan su `edizioni` (317 su 1 000), semi-join con Index Only Scan su `ix_iscrizioni_edizione_stato` | 1 ms |
| Job: edizioni con posti e lista d'attesa (US-09) | Seq Scan su `edizioni` (614 su 1 000), semi-join con Index Only Scan su `ix_iscrizioni_lista_attesa` | 1 ms |
| Primo in lista d'attesa | Index Scan su `ix_iscrizioni_lista_attesa`, si ferma alla prima riga | 0,09 ms |
| Audit di un'iscrizione | Index Scan su `ix_eventi_audit_iscrizione` | 0,2 ms |

Indici non creati, di proposito: `edizioni.docente_id` ed `eventi_audit.autore_id`. Nessuna ricerca dell'API filtra per docente o per autore, e le persone non si cancellano, quindi PostgreSQL non deve mai cercare le righe che le referenziano. Da riconsiderare con le presenze del docente (US-12) e con eventuali report per autore.

Il catalogo filtra per titolo con `ILIKE '%…%'`, che non usa indici: con poche migliaia di corsi la scansione è trascurabile; con molti di più servirebbe un indice trigrammi (`pg_trgm`).

Le due ricerche del job leggono tutte le edizioni del lato giusto di oggi: con queste proporzioni la scansione sequenziale costa meno dell'indice. Le edizioni passate crescono nel tempo, ma il job gira ogni cinque minuti e ogni edizione in più costa microsecondi; un limite inferiore sulla data non serve, perché una pendente su un'edizione iniziata si chiude alla prima passata.

US-07 è stata riscritta dopo la misura. La prima versione cercava il responsabile di ogni richiedente con una sottoquery correlata (`ORDER BY livello LIMIT 1` sugli antenati del suo team): PostgreSQL la rieseguiva per ognuna delle 5 000 persone, dopo una scansione sequenziale delle 7 142 iscrizioni `Richiesta`, e impiegava 100-185 ms per ciascuna delle due query della rotta (conteggio e pagina). La versione attuale calcola il responsabile di tutte le persone in un colpo solo (CTE `responsabile_di` con `DISTINCT ON (persona) ... ORDER BY persona, livello`), poi filtra quelle del decisore e ne legge le iscrizioni per indice: 10-18 ms, quasi tutti nell'ordinamento delle catene (circa 10 000 righe). Lo script esegue ancora la versione correlata come confronto. Nessun indice nuovo: il tempo non sta in una lettura che un indice eviterebbe. Con molte più persone conviene partire dal decisore e scendere nei soli team in cui è responsabile. `test_l_elenco_coincide_con_chi_puo_decidere` confronta l'SQL con `dominio.organigramma` su ogni coppia di persone, compreso chi guida due team della propria catena.

Il caso istruttivo è la lista d'attesa. Togliendo i due indici su `edizione_id`, PostgreSQL ripiega sull'indice parziale `uq_iscrizioni_attiva`: legge tutte le 29 iscrizioni attive dell'edizione, ne scarta 23 con un filtro e le ordina. Il tempo sale a circa 1 ms, dieci volte tanto. L'indice parziale con `approvata_il` restituisce invece la prima riga già in ordine.
