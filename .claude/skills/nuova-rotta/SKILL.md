---
name: nuova-rotta
description: Aggiunge o cambia una rotta dell'API REST del backend con test di accettazione, riga nella matrice di autorizzazione, contratto OpenAPI versionato e client del frontend rigenerato. Usala quando una issue chiede un endpoint nuovo o un cambio di richiesta/risposta di uno esistente.
---

# Nuova rotta con test

Convenzioni in ADR-0005 (errori RFC 9457, ETag/If-Match, paginazione, nomi). Livelli: rotta → servizio → repository; niente regole nelle rotte, niente SQL fuori dai repository (`CLAUDE.md`, Architettura).

## Passi (da `backend/`)

1. **Criteri di accettazione → test che falliscono.** Un test per criterio in `tests/test_api_<area>.py`, compresi i casi vietati e gli errori. Usa la fixture `client` (identità provvisoria con `X-Persona-Id`), `tests/api.py` e i dati sintetici di `tests/dati.py`. Marca `@pytest.mark.integrazione` se servono il database. Le regole senza HTTP si provano sul servizio.
2. **Schemi** Pydantic di richiesta e risposta in `src/academy_hub/api/schemi.py`; nomi di dominio italiani (`CONTEXT.md`).
3. **Repository** (`repository/`): la query, con i lock nell'ordine di ADR-0004 se scrive (prima l'edizione, poi le iscrizioni).
4. **Servizio** (`servizi/`): regole e autorizzazione. Gli errori sono quelli di `dominio/errori.py`, ognuno con il suo `tipo`; un errore nuovo va lì e nella mappa di `api/errori.py`. Un cambio di stato di un'iscrizione passa dall'unico punto che scrive l'audit (R6); un posto liberato da `promuovi_dalla_lista` (R4).
5. **Rotta** in `api/rotte/<area>.py`: `operation_id` in camelCase (diventa il nome nel client), `responses=risposte(...)` con gli stati d'errore possibili, dipendenze `SessioneDb` e `AttoreCorrente`. Mai `include_in_schema=False`. Un file di rotte nuovo va nella tupla dei router in `main.py`.
6. **Matrice di autorizzazione**: una riga in `MATRICE` di `tests/test_autorizzazione.py` con gli stati attesi per ogni profilo (`_attesi(...)`, `TUTTI`, `SOLO_ADMIN`). Senza riga fallisce `test_ogni_rotta_ha_la_sua_riga`.
7. **Feature flag** se la funzione va accesa per ambiente (ADR-0014): `ACADEMY_FLAG_<NOME>` in `config.py`, dipendenza che risponde 404 da spenta, campo in `FlagFunzioni`, valori in `databricks.yml` (collaudo accesa, prod spenta) e `docker-compose.yml`.
8. **Contratto**: aumenta `VERSIONE_API` in `api/__init__.py` (minore se aggiungi, maggiore se rompi: cambia anche il prefisso `/api/vN`), poi
   ```bash
   uv run python -m academy_hub.contratto
   ```
   e in `frontend/` `npm run api:genera` (rigenera `src/api/schema.d.ts`). Se il frontend usa la rotta: hook in `src/api/`, test Vitest accanto al componente, e2e solo per i flussi principali.
9. **Verifica**:
   ```bash
   uv run ruff check --fix && uv run ruff format && uv run pyright
   uv run pytest                              # completo, con Docker
   cd ../frontend && npm run lint && npm run tipi && npm test
   ```
10. Documentazione nella stessa PR: ADR-0005 se cambia una convenzione, un ADR nuovo per una scelta non ovvia, `CONTEXT.md` per un termine nuovo, `docs/threat-model.md` se la rotta apre una superficie nuova (dati personali, file, identità esterna).

## Errori già visti

- I test che passano senza verificare nulla: controlla stato **e** corpo della risposta, e che lo stato del database sia cambiato (o no, per i casi vietati).
- Una rotta dietro flag spenta risponde 404: i test che girano su tutte le rotte vogliono le flag accese.
- `null` in un `PATCH` è 422, salvo i campi davvero annullabili (ADR-0005).
