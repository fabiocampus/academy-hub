# Backlog iniziale

Fonte delle issue su GitHub. Ogni storia diventa una issue `type:story`, sub-issue della sua feature. Le regole R1–R7 sono definite in [CONTEXT.md](../CONTEXT.md).

Formato dei criteri di accettazione: *Dato / Quando / Allora*. I casi di errore usano la risposta `problem+json` (RFC 9457) con un `type` specifico.

---

## E1 · Catalogo e edizioni

### F1.1 · Gestione dei corsi

#### US-01 · Creare e modificare un corso
**Come** amministratore Academy **voglio** creare e modificare i corsi **per** mantenere aggiornato il catalogo.

- Dato un amministratore, quando crea un corso con titolo, descrizione e durata in ore, allora il corso è visibile nel catalogo.
- Dato un corso, quando la durata è ≤ 0 o il titolo è vuoto, allora la richiesta è rifiutata con `422` e il campo in errore.
- Dato un dipendente o un responsabile, quando prova a creare un corso, allora riceve `403`.
- Dato un corso con edizioni, quando l'amministratore lo archivia, allora non compare più nel catalogo ma le edizioni passate restano nei report.

### F1.2 · Gestione delle edizioni

#### US-02 · Pianificare un'edizione
**Come** amministratore Academy **voglio** creare un'edizione con date e capienza **per** aprire le iscrizioni.

- Dato un corso, quando l'amministratore crea un'edizione con inizio, fine e capienza > 0, allora l'edizione è aperta alle iscrizioni.
- Quando la data di fine precede quella di inizio, o la capienza è ≤ 0, allora la richiesta è rifiutata con `422`.
- Dato un'edizione con iscrizioni confermate, quando l'amministratore riduce la capienza sotto il numero dei confermati, allora la richiesta è rifiutata con `409` (R3).
- Dato un'edizione con lista d'attesa, quando l'amministratore aumenta la capienza, allora i posti nuovi passano ai primi in lista d'attesa (R4).

### F1.3 · Catalogo

#### US-03 · Consultare il catalogo
**Come** dipendente **voglio** vedere le edizioni future con i posti disponibili **per** scegliere a quale iscrivermi.

- Dato un catalogo con edizioni passate e future, quando un dipendente lo consulta, allora vede solo le edizioni non ancora iniziate, ordinate per data di inizio.
- Ogni edizione mostra corso, date, capienza, posti confermati e lunghezza della lista d'attesa.
- Il catalogo è paginato e filtrabile per titolo del corso e intervallo di date.
- Se il dipendente ha già un'iscrizione attiva a un'edizione, il catalogo ne mostra lo stato.

---

## E2 · Iscrizioni e flusso approvativo

### F2.1 · Richiesta d'iscrizione

#### US-04 · Chiedere l'iscrizione
**Come** dipendente **voglio** chiedere l'iscrizione a un'edizione **per** partecipare al corso.

- Dato un'edizione non iniziata, quando il dipendente chiede l'iscrizione, allora nasce un'iscrizione `Richiesta` e un evento di audit (R6).
- Dato un'iscrizione attiva alla stessa edizione, quando il dipendente chiede di nuovo l'iscrizione, allora riceve `409` con `type` `iscrizione-duplicata` (R1).
- Dato una richiesta ripetuta con la stessa chiave di idempotenza, allora la risposta è quella della prima richiesta e non nasce una seconda iscrizione.
- Dato un'edizione già iniziata, quando il dipendente chiede l'iscrizione, allora riceve `409` con `type` `edizione-iniziata`.
- Dato un'iscrizione `Rifiutata` o `Annullata`, quando il dipendente chiede di nuovo l'iscrizione, allora nasce una nuova iscrizione `Richiesta` (D4).

#### US-05 · Vedere le mie iscrizioni
**Come** dipendente **voglio** vedere le mie iscrizioni e il loro stato **per** sapere a che punto sono.

- Il dipendente vede solo le proprie iscrizioni, con edizione, stato attuale e data dell'ultimo cambio.
- Per ogni iscrizione vede la storia dei cambi di stato (dall'audit).
- Per un'iscrizione `InAttesa` vede la propria posizione in lista d'attesa.

### F2.2 · Approvazione

#### US-06 · Approvare o rifiutare una richiesta
**Come** responsabile **voglio** approvare o rifiutare le richieste del mio team **per** decidere chi va in formazione.

- Dato un'iscrizione `Richiesta` di un membro del mio team, quando approvo, allora diventa `Approvata` con audit (R6).
- Quando rifiuto, allora diventa `Rifiutata`; il motivo del rifiuto è obbligatorio.
- Dato un'iscrizione di una persona di un altro team, quando provo ad approvarla, allora ricevo `403` (R2).
- Dato la richiesta di un responsabile, allora la approva il responsabile del team padre; per il team al vertice approva l'amministratore Academy (D7).
- Il responsabile diretto è quello in carica al momento della decisione: se il dipendente cambia team, le richieste pendenti passano al nuovo responsabile (D9).
- Dato una mia richiesta, quando provo ad approvarla, allora ricevo `403` (R2).
- Dato un'iscrizione non in stato `Richiesta`, quando provo ad approvarla, allora ricevo `409` con `type` `transizione-non-consentita` (R7).
- Dato due approvazioni simultanee della stessa richiesta, allora una sola va a buon fine; l'altra riceve `409` (concorrenza ottimistica).

#### US-07 · Elenco delle richieste da approvare
**Come** responsabile **voglio** vedere le richieste del mio team in attesa di decisione **per** non dimenticarne nessuna.

- Vedo solo le iscrizioni `Richiesta` delle persone del mio team, ordinate dalla più vecchia.
- Non vedo le mie richieste in questo elenco.

### F2.3 · Conferma dei posti e lista d'attesa

#### US-08 · Confermare un posto
**Come** amministratore Academy **voglio** confermare le iscrizioni approvate **per** assegnare i posti dell'edizione.

- Dato un'iscrizione `Approvata` e posti disponibili, quando confermo, allora diventa `Confermata` con audit.
- Dato un'iscrizione `Approvata` e posti esauriti, quando confermo, allora diventa `InAttesa` (D1).
- Dato un solo posto libero e due conferme simultanee, allora una sola iscrizione diventa `Confermata`, l'altra `InAttesa` (R3).
- In nessun momento le iscrizioni `Confermata` superano la capienza; lo garantisce anche un vincolo nel database.

#### US-09 · Promozione dalla lista d'attesa
**Come** dipendente in lista d'attesa **voglio** ricevere il posto appena si libera **per** non dover rifare la richiesta.

- Dato una lista d'attesa e un'iscrizione `Confermata` che viene annullata, allora la prima `InAttesa` in ordine di approvazione diventa `Confermata` automaticamente, senza intervento dell'Academy (R4, D2).
- Dato due iscrizioni in lista d'attesa approvate in momenti diversi, allora passa per prima quella approvata prima, anche se richiesta dopo.
- La promozione genera un evento di audit con autore «sistema».
- Dato un'edizione già iniziata, quando si libera un posto, allora nessuno viene promosso (D2).

### F2.4 · Annullamento

#### US-10 · Annullare la propria iscrizione
**Come** dipendente **voglio** annullare la mia iscrizione **per** liberare il posto se non posso partecipare.

- Dato un'iscrizione `Richiesta`, `Approvata` o `InAttesa`, quando la annullo, allora diventa `Annullata` (D3).
- Dato un'iscrizione `Confermata` e mancano più di N giorni di calendario all'inizio (fuso `Europe/Rome`, D11), quando la annullo, allora diventa `Annullata` e parte la promozione dalla lista d'attesa (R4, R5).
- Dato un'iscrizione `Confermata` e mancano N giorni o meno all'inizio, quando la annullo, allora ricevo `409` con `type` `scadenza-annullamento-superata` (R5).
- Dato l'iscrizione di un'altra persona, quando provo ad annullarla, allora ricevo `403`.
- N è letto dalla configurazione dell'ambiente, non dal codice.

#### US-17 · Scadenza delle richieste all'inizio dell'edizione
**Come** amministratore Academy **voglio** che le iscrizioni rimaste pendenti si chiudano all'inizio dell'edizione **per** non avere richieste aperte su corsi già partiti.

- Dato un'edizione che inizia, allora le iscrizioni `Richiesta`, `Approvata` e `InAttesa` diventano `Annullata` con motivo `edizione-iniziata` e autore «sistema» (D8).
- Le iscrizioni `Confermata` non cambiano.
- Il job è idempotente: eseguirlo due volte non genera eventi di audit duplicati.

#### US-18 · Cancellare un'edizione
**Come** amministratore Academy **voglio** cancellare un'edizione **per** gestire un corso che non si può più tenere.

- Dato un'edizione non iniziata, quando la cancello, allora ogni iscrizione attiva diventa `Annullata` con motivo `edizione-cancellata`, anche dentro la scadenza di R5 (D10).
- L'edizione resta nel database come cancellata (cancellazione logica) e sparisce dal catalogo.
- Dato un'edizione già iniziata, quando provo a cancellarla, allora ricevo `409`.

### F2.5 · Audit

#### US-11 · Consultare l'audit di un'iscrizione
**Come** amministratore Academy **voglio** consultare la storia completa di un'iscrizione **per** spiegare ogni decisione.

- Ogni cambio di stato registra autore, istante, stato di partenza, stato di arrivo e motivo se presente (R6).
- Gli eventi di audit non si modificano né si cancellano tramite l'API.
- Una transizione rifiutata (R7) non genera eventi di audit di cambio di stato.

---

## E3 · Presenze e valutazioni

### F3.1 · Presenze

#### US-12 · Caricare il file delle presenze
**Come** amministratore Academy (o docente dell'edizione) **voglio** caricare il file delle presenze **per** registrare chi ha completato il corso.

- Il CSV ha una riga per persona e giornata dell'edizione.
- Dato un CSV valido per un'edizione conclusa, quando lo carico, allora le iscrizioni `Confermata` con presenza ad almeno il 75% delle giornate diventano `Completata`; la soglia è configurabile (D5).
- Le iscrizioni `Confermata` sotto la soglia restano `Confermata` e compaiono nel report come non completate.
- Dato un CSV con persone sconosciute, duplicati o date fuori dall'edizione, allora quelle righe vanno in quarantena con il motivo.
- Dato un CSV con errori gravi (formato non valido, edizione inesistente), allora l'intero file è rifiutato e il motivo è registrato.
- Un docente può caricare solo le presenze delle proprie edizioni; altrimenti riceve `403`.

### F3.2 · Valutazioni

#### US-13 · Valutare un corso completato
**Come** dipendente **voglio** valutare un'edizione che ho completato **per** aiutare l'Academy a migliorare.

- Dato un'iscrizione `Completata`, quando lascio voto da 1 a 5 e commento facoltativo, allora la valutazione è registrata.
- Dato un'iscrizione non `Completata`, quando provo a valutare, allora ricevo `409`.
- Una sola valutazione per iscrizione, non modificabile; un secondo invio riceve `409` (D6).

---

## E4 · Report e qualità dei dati

### F4.1 · Report

#### US-14 · Report del mio team
**Come** responsabile **voglio** vedere ore di formazione, tasso di completamento e valutazioni del mio team **per** pianificare la crescita delle persone.

- Vedo solo i dati del mio team, anche interrogando direttamente le tabelle (row filter in Unity Catalog).
- L'amministratore Academy vede tutti i team.
- Il report mostra la data dell'ultimo aggiornamento riuscito.

### F4.2 · Gate di qualità

#### US-15 · Bloccare i report su dati non validi
**Come** amministratore Academy **voglio** che i report non si aggiornino se i dati importati violano regole gravi **per** non prendere decisioni su numeri sbagliati.

- Dato un'importazione con errori bloccanti, allora le tabelle gold non si aggiornano e l'esito con il motivo è registrato in una tabella dedicata.
- Dato un'importazione con soli errori non bloccanti, allora le righe valide aggiornano i report e quelle non valide restano in quarantena.
- Un controllo fallito genera un avviso.

---

## E5 · Identità e accesso

### F5.1 · Autenticazione e ruoli

#### US-16 · Accedere con la propria identità
**Come** utente **voglio** accedere con la mia identità aziendale **per** usare l'applicazione con i permessi del mio ruolo.

- In locale l'identità arriva da Keycloak (OIDC); su Databricks dall'identità fornita dalla piattaforma all'App.
- Senza identità valida ogni rotta, tranne `/health`, risponde `401`.
- I ruoli applicativi sono gestiti dall'applicazione, non dal provider di identità.
- Ogni azione vietata a un ruolo è rifiutata dall'API con `403`, anche se l'interfaccia non la mostra.

---

## Decisioni emerse dalla revisione

Revisione critica delle storie rispetto al diagramma degli stati e alle regole R1–R7. Le decisioni sono riportate nel diagramma e nel glossario di [CONTEXT.md](../CONTEXT.md).

| # | Domanda | Decisione |
|---|---|---|
| D1 | `Approvata → InAttesa`: alla conferma dell'Academy o subito all'approvazione? | Alla conferma dell'Academy: se non ci sono posti, l'iscrizione va `InAttesa`. L'Academy resta l'unico punto che assegna posti. |
| D2 | `InAttesa → Confermata`: automatica o manuale? Fino a quando? | Automatica, con autore «sistema», nella stessa transazione che libera il posto; un job periodico fa da rete di sicurezza (ADR-0007). Nessuna promozione a edizione iniziata. |
| D3 | Il diagramma originale non prevedeva `InAttesa → Annullata`. | Transizione aggiunta: chi è in lista d'attesa può ritirarsi. |
| D4 | Dopo `Rifiutata` o `Annullata` si può chiedere di nuovo l'iscrizione? | Sì: R1 conta solo le iscrizioni attive. |
| D5 | Che cosa conta come presenza per passare a `Completata`? | Una riga per persona e giornata; `Completata` con almeno il 75% delle giornate. Soglia configurabile. |
| D6 | La valutazione è modificabile? | No: una sola valutazione per iscrizione. *Proposta adottata, modificabile.* |
| D7 | Chi approva le richieste di un responsabile? | Il responsabile del team padre; per il team al vertice l'amministratore Academy. I team formano una gerarchia. |
| D8 | Richieste pendenti all'inizio dell'edizione? | Diventano `Annullata` con motivo `edizione-iniziata`, tramite job. Anche le `InAttesa`. |
| D9 | Richieste pendenti se il dipendente cambia team? | Le decide il responsabile in carica al momento della decisione. *Proposta adottata, modificabile.* |
| D10 | Cancellazione di un'edizione con iscrizioni attive? | Tutte `Annullata` con motivo `edizione-cancellata`, ignorando R5; cancellazione logica dell'edizione. |
| D11 | N giorni di R5: calendario o lavorativi? Fuso orario? | Giorni di calendario, fuso `Europe/Rome`, confronto sulla data di inizio. *Proposta adottata, modificabile.* |
