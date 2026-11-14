# Threat model del flusso di approvazione

- **Metodo:** STRIDE per elemento del flusso, sul sistema com'è alla fine della fase 6 (issue #56); aggiornato con il frontend servito dallo stesso processo (fase 7, issue #66).
- **Perimetro:** richiesta, approvazione o rifiuto, conferma, annullamento, job di sistema. Fuori perimetro: la parte analitica su Databricks (fase 8 e seguenti), Keycloak stesso. Del frontend (fase 7) ci sono le minacce sull'accesso e sul browser (XSS, clickjacking, file serviti).
- **Da rivedere:** quando cambia il provider d'identità, prima del primo deploy su Databricks Apps.

## Il sistema

```mermaid
flowchart LR
    U([Persona]) -- "Bearer JWT (locale)<br/>X-Forwarded-Email (Databricks)" --> API
    KC[(Keycloak<br/>realm academy)] -. "JWKS (cache 5 min)" .-> API
    subgraph confine["Confine di fiducia: backend"]
        API[FastAPI<br/>rotte → servizi → repository]
        JOB[Job di sistema]
    end
    API -- "una transazione<br/>per richiesta" --> DB[(PostgreSQL<br/>persone, iscrizioni, audit)]
    JOB -- "una transazione<br/>per edizione" --> DB
```

| Passo | Rotta | Chi può (matrice in `backend/tests/test_autorizzazione.py`) |
|---|---|---|
| Richiesta | `POST /iscrizioni` | ruolo `dipendente`, per sé |
| Approvazione, rifiuto | `POST /iscrizioni/{id}/approvazione`, `/rifiuto` | solo il responsabile diretto del richiedente (R2), mai su sé stesso; per le richieste dal vertice un `admin_academy` |
| Conferma | `POST /iscrizioni/{id}/conferma` | `admin_academy` |
| Annullamento | `POST /iscrizioni/{id}/annullamento` | il titolare; se `Confermata`, solo entro la scadenza (R5) |
| Job | `python -m academy_hub.job` | nessuna rotta: processo con le credenziali del database |

Asset da proteggere: l'esito delle richieste (chi va al corso), i posti delle edizioni, la storia di audit, i dati personali minimi (nome, email, team).

## Difese che ci sono già

| Id | Difesa | Dove |
|---|---|---|
| D1 | Token OIDC verificato: solo RS256, chiavi dal JWKS, `iss`, `aud`, `exp`, `iat` obbligatori, `email_verified` | `api/identita.py`, ADR-0008 |
| D2 | Ruoli e team solo dal database, mai dal token o dagli header | `api/dipendenze.py`, ADR-0008 |
| D3 | Identità `provvisoria` (`X-Persona-Id`) e `databricks` rifiutate dalla configurazione fuori dall'ambiente giusto | `config.py` |
| D4 | Autorizzazione nei servizi, prima di leggere lo stato: chi non può decidere non scopre lo stato (R2 prima di R7) | `servizi/`, `dominio/organigramma.py` |
| D5 | Matrice rotta × profilo eseguita in CI, con profili dello stesso ruolo dentro e fuori dal rapporto con l'iscrizione (titolare, responsabile diretto); una rotta senza riga fa fallire i test | `tests/test_autorizzazione.py` |
| D6 | Transizioni ammesse in un solo punto, con audit nella stessa transazione | `servizi/iscrizioni.py`, R6, R7 |
| D7 | Audit append-only: un trigger blocca `UPDATE`, `DELETE`, `TRUNCATE` | migrazione 0001, `docs/database.md` |
| D8 | Lock in ordine fisso (edizione, poi iscrizioni), posti contati sotto lock, vincoli `CHECK` | ADR-0004 |
| D9 | Idempotenza della richiesta (`Idempotency-Key`), concorrenza ottimistica su corsi ed edizioni (`If-Match`) | ADR-0005, ADR-0006 |
| D10 | Errori RFC 9457 senza stack trace; il motivo del rifiuto del token solo nel log | `api/errori.py`, ADR-0008 |
| D11 | Input con limiti (lunghezze, paginazione al massimo 100, `extra="forbid"`) | `api/schemi.py` |
| D12 | Catena di fornitura: azioni fissate per SHA, immagini per digest, Dependabot, `pip-audit` su `uv.lock`, Trivy sull'immagine, CodeQL (Python e Actions), gitleaks e secret scanning con push protection | `.github/` |
| D13 | Container non root, porte di compose solo su `127.0.0.1` | `backend/Dockerfile`, `docker-compose.yml` |
| D14 | HTML dell'app con `Content-Security-Policy` (script solo dalla stessa origine, nessun `object`, `base-uri` e `form-action` limitati, `frame-ancestors 'none'`, rete solo verso l'app e l'emittente OIDC), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`; file serviti solo da dentro la build, `/api` mai coperto dal fallback | `academy_hub/frontend.py`, ADR-0009 §14 |

## Minacce

Stato: **mitigata** (una difesa la copre), **accettata** (rischio residuo consapevole, con il motivo), **aperta** (da fare, con la fase).

### S · Spoofing

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| Token falsificato o firmato con `alg: none` / HS256 con la chiave pubblica | tutti | D1 | mitigata |
| Token di un altro realm o per un altro servizio | tutti | D1 (`iss`, `aud`) | mitigata |
| Email non verificata usata per agganciare la persona di un altro | tutti | D1 (`email_verified`) | mitigata |
| `X-Persona-Id` o `X-Forwarded-Email` mandati a mano | tutti | D3 | mitigata fuori da `locale` e con `oidc`; in locale `provvisoria` permette di impersonare chiunque (voluto, per i test). Su Databricks l'App è raggiungibile solo dal proxy, da verificare nella fase 8 |
| Deploy senza `ACADEMY_AMBIENTE`: vale `locale`, quindi `provvisoria` passa la validazione | tutti | D3 dipende da `ACADEMY_AMBIENTE` impostato | aperta (#58): nella fase 8 il deploy su Databricks lo imposta e un controllo all'avvio lo rende obbligatorio fuori dai test |
| Token rubato riusato fino alla scadenza | tutti | durata breve del token di Keycloak | accettata: niente binding (DPoP, mTLS) in un prototipo |
| Utente rinominato nel provider che prende l'email di un ex collega | tutti | email unica in `persone`; il cambio va fatto a mano | accettata (ADR-0008) |

### T · Tampering

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| Saltare l'approvazione (`Richiesta` → `Confermata`) | conferma | D6: la conferma parte solo da `Approvata` | mitigata |
| Approvare la propria richiesta, o quella di chi non dipende da me | approvazione | D4 (`AutoApprovazione`, `NonResponsabileDiretto`) | mitigata |
| Annullare l'iscrizione di un altro | annullamento | D4: solo il titolare | mitigata |
| Superare la capienza con conferme simultanee | conferma, annullamento, job | D8 | mitigata |
| Riscrivere o cancellare la storia | tutti | D7 | mitigata per l'app; un superutente del database può spegnere i trigger |
| Modifica di corso o edizione sopra quella di un altro | — | D9 | mitigata |
| Organigramma cambiato per farsi approvare da un complice | approvazione | nessuna rotta modifica team o responsabili: si cambiano solo nel database | accettata finché non c'è un'API dell'organigramma |

### R · Repudiation

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| «Non l'ho approvata io» | approvazione, rifiuto, conferma, annullamento | D6, D7: evento con autore, stato prima e dopo, istante del database | mitigata |
| Cambi fatti dal job senza autore | job | eventi con autore `NULL` = sistema, una transazione per edizione (ADR-0007) | mitigata |
| Log applicativi senza correlazione (chi, quale richiesta) | tutti | — | aperta: fase 9 (osservabilità, OpenTelemetry) |

### I · Information disclosure

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| Leggere l'iscrizione e la storia di un altro | lettura | D4: solo il titolare o `admin_academy` | mitigata |
| Scoprire che un'iscrizione esiste: per un id altrui la risposta è 403, non 404, e gli id sono sequenziali | lettura, decisioni, annullamento | — | accettata: rivela solo l'esistenza di un numero, non chi né dove |
| Elenco delle richieste altrui | US-07 | la query applica la stessa regola del decisore, verificata da un test | mitigata |
| Dettagli interni negli errori | tutti | D10 | mitigata |
| Segreti nel repository pubblico | — | D12 (gitleaks in pre-commit e in CI, push protection), solo dati sintetici | mitigata |
| `GET /configurazione` è pubblica e rivela emittente OIDC e client id del frontend | accesso | solo dati già visibili nella pagina di login; il client è pubblico (PKCE, nessun segreto) | accettata (fase 7, ADR-0009) |
| Access token rubato dal browser con uno script iniettato (XSS): con l'HTML sulla stessa origine dell'API uno script vale una sessione intera | tutti | React fa l'escape del testo, nessun HTML grezzo; D14 (CSP: niente script inline o di altre origini, dati mandati solo all'app o all'emittente); token in `sessionStorage`, non in `localStorage`; durata breve del token di Keycloak | mitigata; resta `style-src 'unsafe-inline'` per gli stili di Mantine (iniezione di CSS, non di script) |
| File del server letti dal fallback della SPA (`../`, percorsi assoluti, collegamenti) | — | D14: percorso risolto e accettato solo dentro la build; test con un file sentinella accanto alla build | mitigata |

### D · Denial of service

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| Molte richieste da un utente autenticato | tutti | D11 (paginazione, lunghezze) | accettata: nessun limite di frequenza; in produzione lo darebbe il proxy di Databricks |
| Lock tenuti a lungo su un'edizione per bloccare le conferme | conferma, annullamento | transazioni brevi; il titolare dell'annullamento è controllato prima dei lock | mitigata in parte: un utente qualunque che tenta una decisione blocca per un attimo la riga dell'iscrizione |
| Percorsi con caratteri nulli che fanno sollevare un errore al file system (500 e righe di log a volontà, senza login) | — | D14: 404 prima di toccare il file system, con test | mitigata |
| Keycloak irraggiungibile | tutti | cache del JWKS 5 minuti, poi 503 `identita-non-disponibile` | accettata |
| Un'edizione che fa fallire il job ferma le altre | job | una transazione per edizione, errori isolati, uscita 1 (ADR-0007) | mitigata |

### E · Elevation of privilege

| Minaccia | Passo | Difesa | Stato |
|---|---|---|---|
| Ruoli inseriti nel token (`realm_access`) | tutti | D2: ignorati | mitigata |
| Clickjacking: l'app in un iframe di un altro sito per far cliccare «Approva» o «Conferma» | approvazione, conferma | D14 (`frame-ancestors 'none'`) | mitigata |
| Rotta nuova dimenticata senza controllo | tutti | D5 | mitigata per ruolo, titolare e responsabile diretto sulle rotte di oggi; per una rotta nuova con un controllo sull'oggetto diverso serve aggiungere il profilo che lo mette alla prova |
| `admin_academy` che decide al posto del responsabile | approvazione | D4: decide solo il responsabile diretto; l'admin solo per le richieste dal vertice | mitigata |
| Dipendenza vulnerabile (Python, immagine, azioni) | — | D12 | mitigata per le vulnerabilità note |
| Codice vulnerabile o workflow iniettabile | — | D12 (CodeQL `security-extended`, permessi minimi nei workflow) | mitigata in parte |

## Rischi accettati e limiti del piano gratuito

- Secret scanning per pattern generici (non legati a un provider) e controllo di validità dei segreti richiedono GitHub Advanced Security: restano spenti. Copre gitleaks.
- Nessun limite di frequenza, nessun binding del token, nessuna cifratura applicativa dei dati personali: sono dati sintetici di un prototipo.
- Il realm Keycloak di sviluppo ha password banali e il password grant (ADR-0008, punto 7): mai in un realm condiviso.
