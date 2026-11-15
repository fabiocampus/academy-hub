# ADR-0018 · Report sul gold e row filter per team

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 11, PR B2 (issue #105, parte di #91). Il gold calcolato dal job `analisi` (ADR-0017) va mostrato dall'App al posto della tabella sintetica della fase 8, letto con l'identità dell'utente (ADR-0011). Tutti gli `account users` hanno `SELECT` sullo schema gold: senza altro, chiunque vedrebbe le ore di formazione di ogni team e le iscrizioni concluse di ogni persona (`gold.iscrizioni_concluse` ha `persona_id`).

## Decisione

1. **API dei report sul gold** (contratto 1.8.0): `GET /report/ore-per-team`, `/report/tasso-completamento`, `/report/valutazione-media`. Stessa porta `LettoreReport` e stesso adapter (`Gold[T]` in `backend/src/academy_hub/report.py`: SQL fisso, colonne attese, conversione). `GET /report/iscrizioni-per-corso` resta, deprecata.
2. **Row filter** `gold.vede_team(team_id)` su `gold.ore_per_team` e `gold.iscrizioni_concluse`. Vede una riga:
   - il responsabile **attuale** del team (`silver.team.responsabile_id`, versione corrente dello SCD 2), riconosciuto dall'email come fa l'App;
   - chi ha il ruolo `admin_academy` (versione corrente di `silver.persone`);
   - gli amministratori del workspace (`admins`).
   `tasso_completamento` e `valutazione_media` sono per corso, senza team né persone: nessun filtro.
3. La funzione si valuta con i diritti di chi la possiede, il service principal del job: chi legge il gold non legge silver.
4. Il task `gold` crea la funzione e riscrive le tabelle con `CREATE OR REPLACE TABLE … WITH ROW FILTER … AS SELECT`: il filtro c'è dalla prima versione di ogni riscrittura, mai un istante senza.

## Differenza con la regola di approvazione dell'App

| | App: approvazione (R2) | Gold: row filter |
| --- | --- | --- |
| Chi | il **responsabile diretto**, risalendo la catena dei responsabili; nessuno sulle proprie richieste | il responsabile **del team**, senza risalire: un responsabile non vede i team figli |
| Quando conta | il responsabile in carica al momento della decisione | il responsabile di oggi, anche per edizioni passate |
| Team della persona | quello attuale | quello alla fine dell'edizione (ADR-0017) |
| Dove si decide | servizi dell'App, sul database transazionale | Unity Catalog, a ogni lettura, con l'identità di chi legge |

Il gold non serve a decidere, ma a leggere aggregati: basta il team di cui si è responsabili. Estendere ai team figli richiederebbe la gerarchia nel filtro (una query ricorsiva), oggi non necessaria.

## Conseguenze

- Un responsabile che cambia team vede subito il nuovo team e non più il vecchio, anche per i dati storici.
- In Free Edition c'è un solo utente, amministratore: in collaudo il filtro si prova controllando che la funzione e il filtro esistano; un responsabile vero si prova solo con più utenti.
- Synced table verso Lakebase (fase 11, PR C) rimandata: non serve al criterio della fase.
