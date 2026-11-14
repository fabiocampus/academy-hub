# ADR-0006 · Idempotenza della richiesta d'iscrizione: chiave sull'iscrizione e lock sulla persona

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

US-04: «Dato una richiesta ripetuta con la stessa chiave di idempotenza, allora la risposta è quella della prima richiesta e non nasce una seconda iscrizione». Un client che perde la risposta (timeout, rete) ripete la `POST /iscrizioni`. Senza idempotenza R1 impedisce comunque il doppione, ma il client riceve `409 iscrizione-duplicata` per un'operazione andata a buon fine e non sa quale iscrizione è sua.

Le domande da chiudere erano tre: dove tenere la chiave, per quanto tempo, che cosa restituire alla ripetizione. Anche le ripetizioni simultanee vanno gestite: il client ritenta mentre la prima richiesta è ancora in corso.

## Decisione

1. **Header `Idempotency-Key`, facoltativo.** Da 1 a 64 caratteri ASCII stampabili (si consiglia un UUID); un valore malformato è 422. Senza header non c'è idempotenza, e R1 continua a impedire il doppione attivo.
2. **La chiave è una colonna dell'iscrizione.** `iscrizioni.chiave_idempotenza`, con indice `UNIQUE (persona_id, chiave_idempotenza)` parziale sulle chiavi non nulle. La chiave vale per persona: due persone possono usare lo stesso valore. Vive quanto l'iscrizione, quindi niente scadenza e niente job di pulizia.
3. **Ripetizione.** Stessa persona, stessa chiave, stessa edizione: `201` con la stessa iscrizione e lo stesso `Location`. Il corpo riporta lo stato **attuale**, che può essere cambiato dopo la prima risposta (per esempio `Approvata`). Stessa chiave con un'altra edizione: `422` con `type` `chiave-idempotenza-riusata`, come nella bozza IETF *The Idempotency-Key HTTP Header Field*.
4. **Lock sulla persona.** La richiesta blocca l'edizione in lettura (`FOR SHARE`), poi la riga della persona (`FOR NO KEY UPDATE`). Le richieste della stessa persona si mettono in fila: chi arriva dopo legge la chiave e le iscrizioni attive già salvate, quindi i controlli su chiave e R1 sono letture semplici. Gli indici unici restano come rete di sicurezza.
5. **Ordine dei lock.** Prima l'edizione, poi la persona, come in ADR-0004 (edizione, poi iscrizioni). `FOR SHARE` non blocca le altre richieste sulla stessa edizione, ma fa aspettare una conferma o una cancellazione dell'edizione fino alla fine della richiesta. Così la cancellazione (US-18) vede anche le iscrizioni appena nate.

`test_stessa_chiave_simultanea_una_sola_iscrizione` e `test_r1_richieste_simultanee_senza_chiave_una_sola_passa` lanciano richieste insieme da più connessioni. Togliendo il lock sulla persona falliscono con `UniqueViolation`.

## Conseguenze

- **Positive:** nessuna tabella in più, nessuna scadenza da gestire; la chiave è leggibile accanto all'iscrizione che ha creato; le ripetizioni simultanee danno la stessa risposta invece di un errore del database.
- **Negative:** la risposta ripetuta non è identica byte per byte alla prima se lo stato è cambiato. Per questa API va bene: il client vuole sapere quale iscrizione è sua e in che stato è. Le richieste della stessa persona si serializzano; con richieste fatte a mano è irrilevante.

## Alternative considerate

- **Tabella delle risposte con scadenza (24 h):** restituisce la prima risposta identica, ma serve un job di pulizia e si salva il corpo delle risposte, dati personali compresi.
- **Chiave obbligatoria:** più rigorosa, ma complica le chiamate fatte a mano (curl, `/docs`) senza un vantaggio reale, perché R1 copre già il caso peggiore.
- **Intercettare `IntegrityError` invece del lock:** funziona, ma la logica passa per un savepoint e la decodifica del nome del vincolo violato. Il lock rende il flusso lineare e testabile.
