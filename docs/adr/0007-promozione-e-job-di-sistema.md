# ADR-0007 · Promozione dalla lista d'attesa nella stessa transazione e job di sistema

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

R4: un posto liberato passa al primo in lista d'attesa, in ordine di approvazione. D2 vuole la promozione automatica, con autore «sistema», e mai a edizione iniziata. D8 vuole che all'inizio dell'edizione le iscrizioni rimaste pendenti (`Richiesta`, `Approvata`, `InAttesa`) diventino `Annullata` con motivo `edizione-iniziata`. D10 vuole che la cancellazione di un'edizione annulli tutte le iscrizioni attive, ignorando R5.

Un posto si libera in tre modi: il titolare annulla una `Confermata` (US-10), l'amministratore aumenta la capienza (US-02), o, per un errore futuro, il contatore resta sotto la capienza con la lista d'attesa piena. La scadenza di D8, invece, non nasce da nessuna richiesta: dipende solo dal calendario.

## Decisione

1. **Promozione nella stessa transazione che libera il posto.** `servizi.iscrizioni.promuovi_dalla_lista(edizione)` riceve l'edizione già bloccata e, finché `posti_confermati < capienza`, porta in `Confermata` la prima `InAttesa` per (`approvata_il`, `id`). La chiamano l'annullamento, l'aumento di capienza e la conferma dell'Academy. Il dipendente vede il posto assegnato appena la risposta arriva, senza aspettare un job.
2. **La conferma non scavalca la lista.** Prima di decidere fra `Confermata` e `InAttesa`, `conferma_posto` promuove la lista. Con la promozione al punto 1 non dovrebbero mai esserci posti liberi e lista d'attesa insieme. Se capitasse (dati importati, un bug), un'iscrizione appena confermata passerebbe davanti a chi aspetta da prima.
3. **Lock.** L'ordine è quello di ADR-0004: prima l'edizione, poi le sue iscrizioni. La prima della lista si sceglie con `FOR NO KEY UPDATE` e senza `SKIP LOCKED` (ADR-0004, punto 4). Chi cambia una `InAttesa` blocca prima l'edizione, quindi la riga scelta non cambia sotto il lock.
4. **Annullamenti in blocco.** `annulla_attive(edizione, stati, motivo, autore)` è condivisa dalla cancellazione (D10, autore l'amministratore) e dalla scadenza (D8, autore il sistema). Passa da `_cambia_stato` come ogni altro cambio di stato, quindi audit (R6) e contatore restano coerenti.
5. **Cancellazione come comando.** `POST /edizioni/{id}/cancellazione` segue le regole dei cambi di stato delle iscrizioni (ADR-0005, punto 3): lo stato si verifica sotto lock, senza `If-Match`. Restituisce 409 `edizione-iniziata` se l'edizione è iniziata. Su un'edizione già cancellata restituisce l'edizione invariata, così un client che ripete la richiesta non riceve un errore.
6. **Job di sistema.** `python -m academy_hub.job` fa una passata e termina: prima la scadenza (D8) sulle edizioni iniziate con iscrizioni pendenti, poi la rete di sicurezza della promozione sulle edizioni aperte con posti liberi e lista d'attesa. Ogni edizione è una transazione a sé, così i lock restano brevi e un errore non annulla il lavoro già fatto. Il job è idempotente per costruzione: lavora solo su ciò che è ancora da fare, quindi una seconda passata non scrive audit.
7. **Lancio.** In locale il servizio `job` di docker compose ripete la passata con `--ogni` (300 secondi per difetto, variabile `ACADEMY_JOB_OGNI_SECONDI`). Il comando è lo stesso che, nella fase della piattaforma dati, può diventare un Databricks Job programmato. Il calendario è quello di Roma (D11), come nel resto del dominio.

## Conseguenze

- **Positive:**
  - una sola funzione di promozione, testata via HTTP, sui servizi con transazioni simultanee e dal job;
  - la scadenza non dipende da una richiesta che potrebbe non arrivare mai;
  - il job si può lanciare a mano, da compose o da uno scheduler senza modifiche.
- **Negative:**
  - fra l'inizio dell'edizione e il giro del job le iscrizioni pendenti restano tali per qualche minuto. Le regole lo tollerano: richieste, approvazioni e conferme controllano già da sole se l'edizione è iniziata;
  - l'annullamento e l'aumento di capienza tengono il lock dell'edizione un po' più a lungo, una riga promossa per ogni posto liberato.

## Alternative considerate

- **Solo il job, anche per la promozione:** un solo meccanismo, ma il posto resta vuoto fino al giro successivo, e nel frattempo una conferma dell'Academy può prenderlo scavalcando la lista.
- **Trigger nel database sull'annullamento:** promozione sempre garantita, ma la regola R4 finirebbe fuori dai servizi, lontana dai test e dall'audit con autore.
- **Scheduler dentro il backend (thread o APScheduler):** niente servizio in più, ma con più repliche del backend il job girerebbe più volte insieme. Il risultato resterebbe corretto grazie ai lock, a costo però di lavoro duplicato. Inoltre Databricks Apps non garantisce un processo sempre vivo.
