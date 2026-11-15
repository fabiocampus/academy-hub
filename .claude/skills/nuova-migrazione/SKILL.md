---
name: nuova-migrazione
description: Cambia lo schema del database transazionale con una migrazione Alembic compatibile con il rilascio precedente. Usala quando una issue chiede una tabella, una colonna, un vincolo, un indice o un trigger nuovo o diverso in PostgreSQL/Lakebase.
---

# Nuova migrazione

Lo schema cambia solo con una migrazione (`docs/database.md`). Le migrazioni girano all'avvio dell'App, mentre la versione precedente può ancora servire richieste: ogni migrazione deve funzionare con il codice di prima (expand/contract, ADR-0013 §7).

## Prima di scrivere

1. Leggi la issue e `docs/database.md` (tabelle, vincoli, indici).
2. Decidi in quale fase expand/contract sei:
   - **expand**: aggiungi (tabella, colonna nullable o con default, indice, vincolo `NOT VALID` poi validato). Il codice vecchio deve continuare a funzionare.
   - **contract**: togli o rendi obbligatorio solo nel rilascio **dopo** quello che ha smesso di usare la cosa. Mai rinominare una colonna in un passo solo: nuova colonna, copia, codice sulla nuova, poi togli la vecchia.
3. Se la colonna è letta dalla parte analitica (`analisi/src/academy_analisi/tabelle.py`), toglierla o rinominarla rompe `backend/tests/test_contratto_analisi.py`: aggiorna anche `tabelle.py` e la pipeline.

## Passi (da `backend/`)

1. Test prima: un test in `tests/test_vincoli.py` (vincolo) o nel test del servizio che userà lo schema nuovo; deve fallire.
2. Modifica `src/academy_hub/db/modelli.py`.
3. Database locale acceso (`docker compose up -d --wait db migrazioni` dalla radice), poi (`127.0.0.1`: `localhost` su Windows si può bloccare su IPv6):
   ```bash
   export ACADEMY_DATABASE_URL=postgresql+psycopg://academy:academy@127.0.0.1:5432/academy
   uv run alembic revision --autogenerate --rev-id <NNNN> -m "<descrizione_breve>"
   ```
   `<NNNN>` = numero dell'ultima migrazione in `src/academy_hub/db/schema/versions/` + 1, a quattro cifre: gli id sono sequenziali, non esadecimali casuali. Il file prende il nome `AAAAMMGG_NNNN_descrizione.py`.
4. **Rileggi** la migrazione generata:
   - docstring in italiano con la issue e il perché;
   - autogenerate non vede trigger, funzioni, `CHECK` complessi e indici parziali con espressioni: scrivili a mano con `op.execute`, con il loro `downgrade`;
   - niente nome dello schema (`academy`, `academy_collaudo`): ci pensa `search_path` (`db/motore.py`);
   - un `UPDATE` di dati esistenti: commenta che cosa succede se fallisce.
5. `downgrade()` completo: `test_migrazioni.py` fa upgrade → check → downgrade base → upgrade.
6. Verifica:
   ```bash
   uv run python -m academy_hub.db.migrazioni   # sul PostgreSQL locale
   uv run alembic check                         # modelli e migrazioni allineati
   uv run pytest tests/test_migrazioni.py tests/test_vincoli.py
   uv run pytest                                # tutto, prima della PR
   ```
7. Documentazione nella stessa PR: tabella e indici in `docs/database.md`; un ADR solo se la scelta non è ovvia (es. un tipo di lock, un vincolo che regge una regola R1–R7).
8. Se cambiano dati di demo o di prova, aggiorna `db/demo.py` e `db/dati_prova.py`.

## Errori già visti

- Testo con `CHECK` al posto di `ENUM` di PostgreSQL per gli stati: aggiungere uno stato è cambiare un vincolo, senza `ALTER TYPE`.
- I trigger di audit rifiutano `UPDATE`/`DELETE`/`TRUNCATE` su `eventi_audit`: una migrazione che tocca quella tabella li deve rispettare.
- Gli indici delle chiavi esterne non li crea PostgreSQL: aggiungili quando una ricerca li usa e misura con `backend/sql/analisi_indici.sql`.
