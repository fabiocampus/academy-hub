# ADR-0008 · Identità da OIDC in locale e da Databricks Apps, ruoli nell'applicazione

- **Stato:** accettato
- **Data:** 2026-11-14
- **Sostituisce:** il punto 6 di ADR-0005 (identità provvisoria)

## Contesto

US-16: in locale l'identità arriva da Keycloak (OIDC), su Databricks da quella che la piattaforma passa all'App; senza identità valida ogni rotta tranne `/health` risponde 401; i ruoli applicativi li gestisce l'applicazione. Fino alla fase 5 l'attore arrivava dall'header `X-Persona-Id`, che permette di impersonare chiunque.

I due ambienti danno l'identità in forme diverse. Keycloak emette un access token JWT firmato, che il client manda come `Authorization: Bearer`. Databricks Apps mette davanti all'App un proxy che autentica l'utente e aggiunge header come `X-Forwarded-Email`; l'App non è raggiungibile senza passare dal proxy. I servizi controllano i ruoli sull'`Attore` (persona, team, ruoli) e non devono sapere da dove arriva.

## Decisione

1. **Un provider per ambiente, scelto dalla configurazione.** `ACADEMY_IDENTITA` vale `oidc` (predefinito), `databricks` o `provvisoria`. Ogni provider (`api/identita.py`) legge gli header e restituisce *chi* è la persona, mai i suoi ruoli. La dipendenza `AttoreCorrente` legge la persona e i ruoli dal database: servizi e controlli di autorizzazione sono gli stessi sopra ogni provider.
2. **La chiave è l'email.** È presente in entrambi gli ambienti (claim `email` del token, header `X-Forwarded-Email`) ed è già unica in `persone`. Il `sub` sarebbe più stabile, ma è diverso fra Keycloak e Databricks e richiederebbe una colonna per provider. Il vincolo `email_minuscola` (migrazione 0004) tiene le email in minuscolo, e il provider porta in minuscolo quella ricevuta: il confronto è esatto e usa l'indice unico. Se un'email cambia nel provider, va cambiata anche in `persone`.
3. **Validazione del token OIDC.** Firma RS256 con le chiavi del JWKS del realm (cache di 5 minuti; un `kid` sconosciuto fa rileggere il JWKS, così la rotazione delle chiavi funziona). Solo RS256: niente `none` né algoritmi simmetrici scelti da chi manda il token. Obbligatori `exp`, `iat`, `iss` (uguale a `ACADEMY_OIDC_EMITTENTE`) e `aud` (deve contenere `ACADEMY_OIDC_PUBBLICO`, `academy-api`); 30 secondi di tolleranza sull'orologio. L'email deve avere `email_verified: true`, perché è la chiave verso `persone`. I ruoli eventualmente presenti nel token (`realm_access`, ...) sono ignorati.
4. **Risposte.** Identità mancante o non valida: 401 `non-autenticato` con `WWW-Authenticate: Bearer` (RFC 6750). Identità valida ma nessuna persona con quell'email: 403 `persona-non-registrata` (autenticata, non abilitata). JWKS non raggiungibile: 503 `identita-non-disponibile`, perché non si può dire se il token è valido e non è colpa del client. Ruolo insufficiente: 403 `azione-non-consentita`, come prima.
5. **Databricks.** Il provider `databricks` si fida di `X-Forwarded-Email` perché lo scrive il proxy di Databricks Apps. Fuori da quel proxy chiunque può mandarlo: la configurazione rifiuta `databricks` con `ACADEMY_AMBIENTE=locale`. La verifica sulla piattaforma vera arriva con la fase 8.
6. **Identità provvisoria solo per i test.** `provvisoria` (header `X-Persona-Id`) resta per i test HTTP esistenti e per prove manuali in locale; la configurazione la rifiuta fuori da `locale`. Docker compose usa `oidc`.
7. **Realm di sviluppo versionato.** `keycloak/realm-academy.json` si importa al primo avvio di Keycloak (`--import-realm`). Contiene il client pubblico `academy-web` (authorization code con PKCE S256, per il frontend della fase 7), il client `academy-cli` (password grant, solo per script e CI) e utenti di prova con password uguale al nome utente: `dipendente`, `responsabile`, `dirigente`, `admin`, `docente`, `esterna` (senza persona, per il 403). Entrambi i client aggiungono il pubblico `academy-api` con un audience mapper. Email solo su `academy.example` (RFC 2606). `KC_HOSTNAME` fissa l'emittente a `http://localhost:8080` anche per chi chiede il token dalla rete di compose; il backend legge le chiavi da `http://keycloak:8080` (`ACADEMY_OIDC_JWKS_URL`).
8. **Dati demo.** `python -m academy_hub.db.demo` (servizio `demo` di compose, solo con ambiente `locale`) crea le persone degli utenti di prova, con team e ruoli, e un piccolo catalogo. È idempotente. Un test confronta le email con quelle del realm.

## Conseguenze

- Il frontend (fase 7) ottiene il token da Keycloak con PKCE e lo manda come Bearer; su Databricks non manda nulla e l'identità arriva dal proxy.
- `/docs` mostra lo schema `HTTPBearer`: si incolla un token preso con `academy-cli`.
- I test usano `tests/oidc.py`: una chiave RSA generata al volo firma token come Keycloak, senza rete. Il job `compose` della CI prende token veri dal realm importato e percorre il flusso richiesta, approvazione, conferma (`scripts/fumo_identita.py`).
- Password grant e password banali sono accettabili solo perché il realm è di sviluppo e locale; non vanno mai in un realm condiviso.
- Una persona che cambia email nel provider perde l'accesso finché non si aggiorna `persone`: preferibile a un aggancio silenzioso alla persona sbagliata.
