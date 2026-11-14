# ADR-0005 · Convenzioni dell'API: errori, concorrenza ottimistica, contratto, identità provvisoria

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

La fase 5 espone il dominio con FastAPI. Il frontend (fase 7) genererà il client dal contratto OpenAPI, quindi forma degli errori, versioni e regole di aggiornamento vanno fissate prima di scrivere le rotte. L'autenticazione vera arriva nella fase 6, ma le regole di autorizzazione (ruoli, R2) vanno testate già ora.

## Decisione

1. **Livelli.** Rotte → servizi → repository. Le rotte traducono HTTP ↔ servizi e non contengono regole; i servizi verificano ruoli e regole; i repository sono l'unico posto con le query. Ogni richiesta è una transazione (`api/dipendenze.py`): commit se la rotta termina senza errori, rollback altrimenti. La dipendenza usa `scope="function"`, così il commit avviene prima di inviare la risposta.
2. **Errori RFC 9457.** Ogni errore è `application/problem+json` con `type`, `title`, `status`, `detail`, `instance`. `type` è il riferimento relativo `/problemi/<tipo>`, dove `<tipo>` è un attributo stabile dell'errore di dominio (`iscrizione-duplicata`, `transizione-non-consentita`…). Il codice HTTP dipende solo dalla classe base (`dominio/errori.py` → `api/errori.py`): `NonAutenticato` 401, `AzioneNonConsentita` 403, `NonTrovato` 404, `Conflitto` 409, `VersioneNonCorrispondente` 412, `DatiNonValidi` 422, `PrecondizioneRichiesta` 428. I dati non validi aggiungono l'estensione `errori: [{campo, messaggio}]`. Un errore imprevisto diventa 500 con `type: about:blank` e nessun dettaglio nel corpo; il dettaglio va nel log.
3. **Concorrenza ottimistica.** Le risorse modificabili hanno una colonna `versione` (`version_id_col` di SQLAlchemy). Le letture restituiscono `ETag: "<versione>"`; ogni modifica richiede `If-Match`: senza, 428; con un valore diverso o malformato, 412. `If-Match: *` riceve 428: per RFC 9110 vale con qualunque versione, quindi aggirerebbe proprio il controllo che l'header serve a fare. Il servizio confronta la versione sotto lock di riga; `version_id_col` resta come ultima difesa (anche questa diventa 412). Il contatore dei posti incrementa la versione dell'edizione: chi modifica un'edizione dopo una conferma deve rileggerla. I lock pessimistici di ADR-0004 restano per i flussi che contendono un posto.
4. **Paginazione.** `limite` (1–100, predefinito 20) e `offset`; la risposta riporta `elementi`, `totale`, `limite`, `offset`.
5. **Contratto versionato.** `backend/contratto/openapi.json` è il contratto generato; `impronte.json` registra, per ogni `VERSIONE_API`, l'impronta SHA-256 del contratto senza `info.version`. `tests/test_contratto.py` fallisce se l'API non coincide con il file o se il contratto cambia senza un aumento di versione. Semver: minor per le aggiunte compatibili, major per i cambi che rompono i client; il prefisso delle rotte (`/api/v1`) segue la versione maggiore. Si rigenera con `uv run python -m academy_hub.contratto`, che rifiuta di cambiare l'impronta di una versione esistente.
6. **Identità provvisoria.** Fino alla fase 6 l'attore arriva dall'header `X-Persona-Id`, accettato solo con `ACADEMY_IDENTITA_PROVVISORIA=true`. Il flag è falso per difetto (un deploy che non imposta nulla risponde 401 a ogni rotta) e la configurazione rifiuta di caricarsi se è vero con `ACADEMY_AMBIENTE` diverso da `locale`. Lo accendono solo docker compose e la fixture `client` dei test. Un valore non numerico è un'identità non valida (401). Ruoli e team si leggono dal database. La fase 6 sostituisce solo la dipendenza `AttoreCorrente` con la validazione dei token: servizi e test di autorizzazione non cambiano.

## Conseguenze

- **Positive:** un client generato conosce ogni errore possibile di ogni rotta; i test confrontano `type` stabili invece di messaggi; due amministratori che modificano la stessa risorsa non si sovrascrivono in silenzio; un cambio involontario del contratto blocca la CI.
- **Negative:** `If-Match` obbligatorio costa una GET prima di ogni modifica; l'header `X-Persona-Id` permette di impersonare chiunque, per questo serve un flag esplicito, ammesso solo in locale, ed è da togliere nella fase 6.

## Alternative considerate

- **`type` come URL assoluto dereferenziabile:** consigliato dalla RFC, ma richiede un dominio pubblico; il riferimento relativo resta stabile e confrontabile.
- **Versione nel corpo invece dell'ETag:** più semplice per il client, ma non standard HTTP e non sfrutta `If-Match`/412.
- **Contratto confrontato solo con il file, senza impronte:** chi rigenera il file aggiornerebbe il contratto senza accorgersi di aver cambiato l'API pubblicata.
