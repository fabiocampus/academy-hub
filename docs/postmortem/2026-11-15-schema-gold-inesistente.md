# Il task gold scrive in uno schema che non esiste

- **Data**: 2026-11-15 · **Durata**: dalle 23:10 (run fallita) alle 23:21 (rollback in collaudo) · **Ambiente**: collaudo
- **Impatto**: report del collaudo non aggiornati per una passata del job `analisi`; SLO di freschezza (`docs/slo.md`) non toccato, perché il gold precedente restava valido e l'interruzione è durata meno di un'ora. Produzione non toccata: l'approvazione di `prod` è stata rifiutata.
- **Tipo**: incidente **simulato** della fase 12 (#111): l'errore è stato introdotto apposta con la PR #114.

## Cronologia

Orari Europe/Rome.

| Ora | Evento |
|---|---|
| 23:05 | Merge della PR #114 (ece5d6a): il task `gold` riceve `--gold ${var.catalogo}.report` invece di `.gold`. CI verde. |
| 23:09 | Run di Rilascio 43767317585: deploy in collaudo e fumo verdi. 23:10: `prod` rifiutato. |
| 23:10 | Lancio a mano del job `analisi` in collaudo (run 1089391572589169), al posto dello schedule delle 05:00. |
| 23:15 | Fine della run: `gold` FAILED due volte (tentativo e ritentativo serverless), `registra_esito` scrive l'esito `errore`. Run `SUCCESS_WITH_FAILURES`: **nessuna email del job**. |
| 23:15 | Visto che l'email non arrivava, l'operatore ha controllato lo stato della run: il guasto è stato visto a mano, non da un avviso. |
| 23:19 | Alert SQL `academy-qualita-collaudo` lanciato a mano (lo schedule è alle 06:00): TRIGGERED, email ricevuta. |
| 23:19 | Diagnosi dal runbook (punto 1): `[SCHEMA_NOT_FOUND] academy_collaudo.report` nell'output del task. Il parametro l'ha cambiato l'ultimo rilascio (punto 2): rollback (punto 3), run 43768687650 verso la run di Rilascio 43766794266. |
| 23:21 | Rollback in collaudo e fumo verdi. Nuovo lancio del job. |
| — | Correzione su `main` con test (PR di #111). |

## Rilevamento

Previsto: email del job alla run fallita. Non è arrivata: l'avviso aveva un buco.

- `registra_esito` gira con `run_if: ALL_DONE` per scrivere l'esito anche dopo un errore (ADR-0017), e riesce. La run quindi finisce `SUCCESS_WITH_FAILURES`, non `FAILED`, e `email_notifications.on_failure` del job scatta solo con `FAILED`, `TIMED_OUT` o `INTERNAL_ERROR`.
- L'alert SQL ha visto il guasto (esito `errore` in `qualita.esiti`), ma gira una volta al giorno alle 06:00: senza il lancio a mano avrebbe avvisato 7 ore dopo.

## Causa

1. Il parametro di uno schema nel bundle è stato cambiato in un nome che non esiste.
2. Nessun controllo lega i nomi degli schemi in `databricks.yml` a quelli che crea Terraform (`infra/databricks/unity_catalog.tf`): la CI non legge il bundle e `bundle deploy` non verifica i parametri dei task.
3. Il fumo del rilascio controlla l'App (`/health`, `/configurazione`), non il job: il deploy era verde con il job già rotto.
4. L'avviso del job non scatta per come è fatto il job stesso (punto sopra).

## Ripristino

Runbook seguito senza deviazioni: diagnosi (punto 1) con `get-run-output`, rollback (punto 3) con `rollback.yml`, nuovo lancio del job (3.4). Mancava nel runbook: che la run può finire `SUCCESS_WITH_FAILURES` senza email (ora c'è la riga "Task `gold` o `controlli` failed").

## Che cosa ha funzionato, che cosa no

- Ha funzionato: il gate (`gold` non ha scritto nulla di parziale, il gold precedente è rimasto); `registra_esito` ha lasciato la traccia che l'alert ha usato; rollback in 2 minuti; l'approvazione di `prod` ha tenuto la produzione fuori.
- Non ha funzionato: l'email del job; l'alert SQL troppo lento per un guasto della sera; il fumo non tocca la parte analitica.

## Azioni

- [x] Test `backend/tests/test_bundle_schemi.py`: ogni `${var.catalogo}.<schema>` di `databricks.yml` deve essere tra gli schemi di Terraform (PR di #111). Rosso sul commit dell'incidente.
- [x] `email_notifications.on_failure` anche sui task `gold` e `controlli`, che avvisano a ogni tentativo fallito qualunque sia l'esito della run (PR di #111).
- [ ] Valutare un fumo della parte analitica nel rilascio (run del job in collaudo prima dell'approvazione di `prod`): costo e durata (~10 minuti) da pesare; non fatto ora.
