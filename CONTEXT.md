# Glossario del dominio

Termini usati in codice, test, issue e documentazione. Nel codice i nomi restano in italiano per le entità di dominio (`Iscrizione`, `Edizione`), così il linguaggio del business coincide con quello del codice.

## Entità

| Termine | Definizione | Da non confondere con |
|---|---|---|
| **Corso** | Un argomento di formazione con titolo, descrizione e durata in ore. Non ha date. | Edizione |
| **Corso archiviato** | Corso ritirato dal catalogo: non riceve nuove edizioni, ma le sue edizioni restano nei report. | Edizione cancellata |
| **Edizione** | Un'istanza datata di un corso: data di inizio e fine, capienza, eventuale docente. Le iscrizioni si fanno sulle edizioni. | Corso |
| **Capienza** | Numero massimo di iscrizioni `Confermata` per un'edizione. | Numero di richieste |
| **Persona** | Un dipendente con nome, email e team. Ha un ruolo applicativo. L'email (minuscola) la collega all'identità tecnica (ADR-0008). | Utente di Keycloak o di Databricks (l'identità tecnica) |
| **Team** | Gruppo di persone con un solo responsabile. I team formano una gerarchia: ogni team, tranne quello al vertice, ha un team padre. | — |
| **Responsabile diretto** | Per un dipendente: il responsabile del suo team. Per un responsabile: il responsabile del team padre; al vertice, l'amministratore Academy. Conta quello in carica al momento della decisione. In generale: il primo della catena dei responsabili diverso dal richiedente. | Amministratore Academy |
| **Catena dei responsabili** | I responsabili dal team di una persona fino al vertice dell'organigramma; un team senza responsabile si salta. Da qui si ricava il responsabile diretto (`dominio/organigramma.py`). | — |
| **Iscrizione** | La richiesta di una persona di partecipare a un'edizione, con il suo stato. | Presenza |
| **Iscrizione attiva** | Un'iscrizione in stato `Richiesta`, `Approvata`, `InAttesa` o `Confermata`. Al massimo una per persona ed edizione (R1). | — |
| **Lista d'attesa** | Le iscrizioni `InAttesa` di un'edizione, ordinate per momento di approvazione. | — |
| **Promozione** | Passaggio automatico `InAttesa → Confermata` del primo in lista d'attesa quando c'è un posto libero (R4): dopo un annullamento, un aumento di capienza o, come rete di sicurezza, al giro del job. Mai a edizione iniziata o cancellata (D2). | Conferma Academy |
| **Iscrizione pendente** | Un'iscrizione attiva senza posto: `Richiesta`, `Approvata` o `InAttesa`. All'inizio dell'edizione diventa `Annullata` (D8). | Iscrizione attiva |
| **Job di sistema** | Processo periodico (`python -m academy_hub.job`) che annulla le iscrizioni pendenti delle edizioni iniziate e ripara la promozione dove serve (ADR-0007). I suoi eventi hanno autore il sistema. | — |
| **Chiave di idempotenza** | Valore scelto dal client (header `Idempotency-Key`) che rende ripetibile la richiesta d'iscrizione: con la stessa chiave si riceve la stessa iscrizione invece di crearne un'altra (ADR-0006). Vale per persona. | Iscrizione duplicata (R1) |
| **Scadenza di annullamento** | Il numero N di giorni di calendario prima dell'inizio dell'edizione (fuso `Europe/Rome`) oltre il quale un'iscrizione `Confermata` non è più annullabile (R5). Configurabile per ambiente. | — |
| **Edizione cancellata** | Edizione ritirata dall'Academy prima dell'inizio. Resta nel database (cancellazione logica); le sue iscrizioni attive diventano `Annullata`. | Edizione conclusa |
| **Presenza** | Riga importata da file: una persona ha frequentato una giornata di un'edizione. | Iscrizione |
| **Soglia di completamento** | Percentuale minima di giornate presenti per passare a `Completata`. Predefinita 75%, configurabile. | — |
| **Valutazione** | Voto da 1 a 5 e commento facoltativo lasciati da chi ha completato un'edizione. Una per iscrizione, non modificabile. | — |
| **Sistema** | Autore degli eventi di audit generati dai job (promozione dalla lista d'attesa, scadenza all'inizio dell'edizione). | Amministratore Academy |
| **Evento di audit** | Registrazione immutabile di un cambio di stato: chi, quando, stato di partenza, stato di arrivo, motivo. | Log applicativo |

## Stati dell'iscrizione

Le transizioni consentite sono solo queste; ogni altra è rifiutata con un errore esplicito (R7). Decisioni D1–D11 in [docs/backlog.md](docs/backlog.md).

```mermaid
stateDiagram-v2
    [*] --> Richiesta: il dipendente si iscrive
    Richiesta --> Approvata: il responsabile diretto approva
    Richiesta --> Rifiutata: il responsabile diretto rifiuta
    Approvata --> Confermata: conferma Academy, posto disponibile
    Approvata --> InAttesa: conferma Academy, posti esauriti
    InAttesa --> Confermata: si libera un posto (sistema)
    Richiesta --> Annullata
    Approvata --> Annullata
    InAttesa --> Annullata
    Confermata --> Annullata: entro la scadenza, o edizione cancellata
    Confermata --> Completata: presenze sopra la soglia
    Rifiutata --> [*]
    Annullata --> [*]
    Completata --> [*]
```

| Da | A | Chi | Condizione |
|---|---|---|---|
| — | `Richiesta` | dipendente | edizione non iniziata né cancellata; nessuna iscrizione attiva alla stessa edizione (R1) |
| `Richiesta` | `Approvata` / `Rifiutata` | responsabile diretto | non sulle proprie richieste (R2); `Approvata` solo con l'edizione non iniziata né cancellata; `Rifiutata` sempre, con motivo obbligatorio |
| `Approvata` | `Confermata` / `InAttesa` | admin Academy | edizione non iniziata né cancellata; `Confermata` se ci sono posti (R3), altrimenti `InAttesa` |
| `InAttesa` | `Confermata` | sistema | primo in ordine di approvazione (R4); solo prima dell'inizio |
| `Richiesta`, `Approvata`, `InAttesa` | `Annullata` | titolare; sistema all'inizio dell'edizione; admin se cancella l'edizione | — |
| `Confermata` | `Annullata` | titolare; admin se cancella l'edizione | il titolare solo fino a N giorni prima dell'inizio (R5) |
| `Confermata` | `Completata` | importazione presenze | presenze ≥ soglia di completamento |

Un'iscrizione è **attiva** in `Richiesta`, `Approvata`, `InAttesa`, `Confermata`. Dopo `Rifiutata` o `Annullata` si può chiedere di nuovo l'iscrizione.

## Ruoli applicativi

| Ruolo | Codice |
|---|---|
| Dipendente | `dipendente` |
| Responsabile | `responsabile` |
| Amministratore Academy | `admin_academy` |
| Docente | `docente` |

Una persona può avere più ruoli: un responsabile è anche dipendente.

## Regole di business

| Codice | Regola |
|---|---|
| R1 | Al massimo una iscrizione attiva per persona ed edizione. |
| R2 | Solo il responsabile diretto approva; nessuno approva le proprie richieste. |
| R3 | Le iscrizioni confermate non superano mai la capienza, anche con conferme simultanee. |
| R4 | Un posto liberato passa al primo in lista d'attesa, in ordine di approvazione. |
| R5 | Un'iscrizione confermata è annullabile solo fino a N giorni prima dell'inizio. |
| R6 | Ogni cambio di stato genera un evento di audit. |
| R7 | Le transizioni non previste sono rifiutate con un errore esplicito. |

## Report

| Termine | Definizione |
|---|---|
| **Ore di formazione** | Somma delle ore dei corsi con iscrizione `Completata`, per persona o team. |
| **Tasso di completamento** | Iscrizioni `Completata` diviso iscrizioni `Confermata` o `Completata` di edizioni concluse. |
| **Snapshot** | Copia giornaliera delle tabelle dell'App in `bronze`, con l'istante dello scatto (`_snapshot_il`); solo in aggiunta; ogni passata riuscita è registrata in `bronze.scatti`, anche per le tabelle vuote (ADR-0016). Non è un backup. |
| **Storico (SCD 2)** | In `silver`, ogni versione di una riga con il suo intervallo di validità (`__START_AT`, `__END_AT`, aperto se è quella corrente), ricavato dagli snapshot. Diverso dall'audit, che registra i cambi di stato. |
| **Bronze, silver, gold** | I livelli del catalogo di un ambiente: dati grezzi come arrivano, dati puliti e storicizzati, aggregati dei report. Gli utenti leggono solo gold. |
| **Importazione** | Un file CSV di presenze o valutazioni caricato nel volume `bronze.importazioni`; la persona si riconosce dall'email (ADR-0017). Un file si legge una volta: una correzione è un file nuovo. |
| **Quarantena** | Tabella che raccoglie le righe scartate di un file importato, come sono arrivate e con il motivo (`qualita.presenze_quarantena`, `qualita.valutazioni_quarantena`). |
| **Regola bloccante** | Regola di qualità la cui violazione, anche in una sola riga, fa respingere l'intero file: edizione inesistente, giorno futuro. |
| **File respinto** | File importato con almeno una riga bloccante o con più del 10% di righe scartate. Le sue righe non arrivano mai nel gold. | Riga in quarantena |
| **Verdetto** | Accettato o respinto: la decisione del gate su un file importato, presa la prima volta che il job lo vede e mai più cambiata (`qualita.verdetti`). |
| **Gate di qualità** | Task `controlli` del job `analisi`: fissa i verdetti dei file nuovi e, se uno è respinto, ferma l'aggiornamento del gold in quella passata. |
| **Esito** | Com'è andata una passata del job: `aggiornato` (gold riscritto), `bloccato` (file respinti, con il motivo) o `errore` (`qualita.esiti`). |
| **Giornate dell'edizione** | I giorni di calendario dal primo all'ultimo compresi: la base della soglia di completamento. |
