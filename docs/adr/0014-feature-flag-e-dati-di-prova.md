# ADR-0014 · Feature flag per ambiente e dati di prova del collaudo

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 10 (issue #81, #86): con il rilascio continuo (ADR-0013) ogni merge su `main` arriva in produzione dopo un'approvazione. Serve un modo per rilasciare codice di una funzione nuova senza renderla visibile in produzione finché non è stata provata in collaudo, e per accenderla senza un nuovo build. Il caso d'esempio è l'evento di calendario (`.ics`) di un'iscrizione Confermata.

Il collaudo, inoltre, nasce vuoto (solo la persona amministratrice di ADR-0010): elenchi, approvazioni e report si provano male senza volume.

Vincoli: un solo artifact per collaudo e prod (ADR-0013 §4), configurazione solo da variabili d'ambiente (`config.py`), repository pubblico (niente dati reali).

## Decisione

1. **Una flag è una variabile d'ambiente booleana** `ACADEMY_FLAG_<NOME>` in `config.py`, **spenta per difetto**. Nessun servizio di feature flag esterno: per un'App e due ambienti basta la configurazione, versionata con il codice.
2. **Il valore per ambiente lo decide il bundle**: una variabile per flag in `databricks.yml` (default `"false"`), sovrascritta nei target. Collaudo accesa, prod spenta. In locale `docker-compose.yml` la accende, così l'end-to-end la prova.
3. **Accendere in produzione è una PR** che cambia la riga del target `prod`: revisione, CI, rilascio con approvazione. Lo stesso artifact già in prod, con la flag diversa (il deploy riavvia l'App con il nuovo ambiente).
4. **Da spenta la funzione non esiste**: la rotta risponde 404 `/problemi/funzione-non-disponibile` (`FunzioneNonDisponibile`), controllato come dipendenza del decoratore della rotta, prima dell'identità: chi chiama non distingue una flag spenta da una rotta che non c'è. Il contratto OpenAPI documenta la rotta in ogni ambiente.
5. **Il frontend legge le flag** da `GET /api/v1/configurazione` (pubblica, campo `flag`) prima del primo render e nasconde ciò che è spento (`api/flag.ts`, contesto React; senza configurazione tutto spento). Nasconderlo è comodità, non sicurezza: la garanzia è il 404 dell'API.
6. **Una flag è temporanea.** Quando la funzione è stabile in produzione, una PR toglie la flag (variabile, controllo, campo in `configurazione`, righe del bundle) e la funzione resta sempre attiva. Una flag mai tolta diventa un ramo di codice in più da testare.
7. **I test coprono entrambi gli stati**: API (404 da spenta, 200 da accesa), matrice di autorizzazione con la flag accesa, frontend con il pulsante assente e presente.
8. **Dati di prova del collaudo** (`db/dati_prova.py`): con `ACADEMY_DATI_PROVA=true` l'avvio dell'App (`avvio.py`), dopo migrazioni e amministratore, carica un insieme deterministico (seme fisso) di team, persone `@academy.example` (RFC 2606: nessuno entra con queste identità), corsi, edizioni e iscrizioni. Le iscrizioni passano dai servizi, con audit, posti e lista d'attesa veri. Una transazione; se il vertice esiste già non fa nulla. È una variabile del bundle accesa solo in collaudo, e la configurazione la **rifiuta in produzione** (validatore in `config.py`): l'App di prod con quella variabile non parte.

## Conseguenze

- Una funzione nuova arriva in prod spenta senza rami di rilascio: il trunk resta unico (rilascio continuo).
- Il cambio di una flag è tracciato come ogni altra modifica (PR, rilascio, deployment dell'environment `prod`): entra nelle metriche DORA come un rilascio.
- Il 404 da spenta nasconde la funzione anche al test di fumo di prod: si verifica in collaudo, a mano, prima della PR di accensione.
- I dati di prova restano nel database di collaudo fino a un branch Lakebase nuovo; le persone sintetiche non hanno un login, quindi non sostituiscono gli utenti di prova veri.
- Prima flag: `ACADEMY_FLAG_CALENDARIO` (`GET /api/v1/iscrizioni/{id}/calendario.ics`, RFC 5545, solo titolare e solo Confermata).
