# ADR-0004 · Concorrenza sull'ultimo posto: lock pessimistico e contatore vincolato

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

R3: le iscrizioni `Confermata` di un'edizione non superano mai la capienza, nemmeno con conferme simultanee. Con il livello di isolamento predefinito di PostgreSQL (`READ COMMITTED`), due transazioni che contano i posti occupati e poi confermano leggono lo stesso numero e confermano entrambe: l'aula è sovraffollata.

Il problema si presenta su ogni ingresso in `Confermata`: la conferma dell'Academy (US-08) e la promozione dalla lista d'attesa (US-09).

## Decisione

1. **Contatore nell'edizione.** `edizioni.posti_confermati` conta le iscrizioni `Confermata`. Lo aggiorna solo il servizio, mai una query sparsa.
2. **Lock pessimistico.** Chi cambia il contatore prima blocca l'edizione con `SELECT … FOR UPDATE` (`repository.iscrizioni.blocca_edizione`). Le conferme sulla stessa edizione si mettono in fila; chi arriva dopo legge il contatore aggiornato e mette l'iscrizione `InAttesa`.
3. **Ordine dei lock.** In tutto il codice si blocca prima l'iscrizione e poi la sua edizione, così due transazioni non si bloccano a vicenda (deadlock).
4. **Vincolo di sicurezza.** `CHECK (posti_confermati BETWEEN 0 AND capienza)`: se un giorno il codice dimenticasse il lock e aggiornasse il contatore con `posti_confermati + 1`, il database rifiuterebbe comunque il posto in più.

Il test `test_r3_conferme_simultanee_sull_ultimo_posto_ne_passa_una_sola` lancia 2 e 10 conferme insieme sull'ultimo posto. Ne passa sempre una sola. Togliendo i `FOR UPDATE`, falliscono entrambi i casi in modo ripetibile.

## Conseguenze

- **Positive:** semplice da leggere e da testare; la serializzazione è limitata alla singola edizione, quindi le conferme su edizioni diverse non si aspettano; il vincolo nel database copre anche gli errori futuri.
- **Negative:** il contatore è un dato derivato e va tenuto coerente: ogni uscita da `Confermata` verso `Annullata` deve decrementarlo (da implementare con US-10 e US-18). Un'edizione molto contesa serializza le conferme, accettabile con capienze da aula.

## Alternative considerate

- **Isolamento `SERIALIZABLE`:** corretto senza lock espliciti, ma sposta il problema nella gestione dei fallimenti di serializzazione, con tentativi da ripetere in ogni chiamante. Più difficile da spiegare e da testare.
- **Concorrenza ottimistica con un campo versione sull'edizione:** adatta agli aggiornamenti dall'interfaccia (fase 5), ma sull'ultimo posto produce errori da ritentare invece di una coda ordinata.
- **Contare le righe `Confermata` sotto lock, senza contatore:** niente dato derivato, ma nessun vincolo dichiarativo possibile: il database non potrebbe più fare da rete di sicurezza.
