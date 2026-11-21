# Runbook

Cosa fare quando arriva un avviso. Gli SLO che gli avvisi proteggono: `docs/slo.md`. Comandi dal PC, profilo `academy` (sola lettura e run manuali; mai `bundle deploy` con questo profilo, vedi `CLAUDE.md`).

## Avvisi

| Avviso | Da | Quando |
|---|---|---|
| Job `academy-analisi-<target>` failed | email del job (`email_notifications.on_failure`) | ogni run fallita, anche dopo i ritentativi |
| Task `gold` o `controlli` failed | email del task (`email_notifications.on_failure` del task) | ogni tentativo fallito: la run finisce `SUCCESS_WITH_FAILURES` perché `registra_esito` gira sempre, e l'email del job non parte |
| Pipeline `academy-storico-<target>` update failed | email della pipeline (`notifications`) | aggiornamento fallito |
| Alert `academy-qualita-<target>` triggered | alert SQL | alle 06:00, esito `bloccato` o `errore` nelle ultime 24 ore |
| Rilascio o Rollback failed | email di GitHub Actions | deploy o fumo falliti |

## 1. Capire che cosa è fallito

```bash
databricks jobs list-runs --job-id <id del job> --limit 5 -o json -p academy   # id nell'email o: databricks jobs list -p academy
databricks jobs get-run <run_id> -o json -p academy        # stato di ogni task
databricks jobs get-run-output <task_run_id> -p academy    # errore e traceback del task
```

```sql
SELECT * FROM <catalogo>.qualita.esiti ORDER BY registrato_il DESC LIMIT 5;
```

- Esito `bloccato`: un CSV respinto dai controlli (motivo nella colonna `motivo`, righe in `<catalogo>.qualita`). **Non è un guasto**: il gate ha fatto il suo lavoro. Si corregge il file alla fonte e lo si ricarica nel volume con un nome nuovo (ADR-0017); il gold resta quello del giorno prima.
- Esito `errore` o task fallito: guasto. Continua al punto 2.

## 2. È colpa dell'ultimo rilascio?

- Commit in esercizio: `/health` dell'App (`rilascio`) oppure l'ultima run verde di "Rilascio" in Actions.
- Se il guasto è iniziato dopo un rilascio e l'errore punta a codice cambiato in quel commit: **rollback** (punto 3), poi la correzione con calma.
- Se no (dati, permessi, piattaforma): diagnosi sui log, correzione con una PR.

### Fumo con `/health` 502 dopo «App started successfully»

L'App parte ma il processo muore subito (`databricks apps get academy-hub-<target> -p academy`, `<target>` = `collaudo` o `prod`: `app_status.state` = `CRASHED`). Leggi i log:

```bash
databricks apps logs academy-hub-<target> -p academy --tail-lines 120
```

Se l'errore è `The endpoint has been disabled. Enable it using the API and retry.`, l'endpoint Lakebase del branch è disabilitato (successo il 2026-11-21 a collaudo e production insieme, dopo un giorno senza uso; il bundle non lo fa). Non è colpa del rilascio: niente rollback.

```bash
databricks postgres list-endpoints projects/academy-hub/branches/<branch> -p academy -o json   # cerca status.disabled: true
databricks postgres update-endpoint projects/academy-hub/branches/<branch>/endpoints/primary spec.disabled --json '{"spec":{"disabled":false}}' -p academy
```

`<branch>` è `collaudo` o `production`: possono essere disabilitati insieme, quindi controllali e riabilitali tutti e due prima di rilanciare. Poi rilancia il job fallito: `gh run rerun <run_id> --failed`.

## 3. Rollback (ADR-0015)

1. In Actions rifiuta i job `prod` di "Rilascio" in attesa e non fare merge finché il rollback non finisce.
2. `gh workflow run rollback.yml -f run_id=<id dell'ultima run di Rilascio buona>`.
3. Il rollback rilascia l'artifact di quella run in collaudo (fumo), poi chiede l'approvazione di `prod`.
4. Per un guasto della parte analitica rilancia il job: `databricks jobs run-now <id del job> --timeout 30m -o json -p academy`.
5. Verifica: run `SUCCESS`, nuova riga `aggiornato` in `qualita.esiti`, fumo verde.

## 4. Chiusura

- Correzione con una PR che ripristina `main` (revert o fix) e porta un test che avrebbe fermato il guasto.
- Post-mortem senza colpa in `docs/postmortem/AAAA-MM-GG-<titolo>.md` (modello: `docs/postmortem/README.md`) entro due giorni.
