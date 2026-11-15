# SLI e SLO

Due indicatori, misurati sulla produzione, finestra di 30 giorni. Gli avvisi che li proteggono e cosa fare quando scattano: `docs/runbook.md`.

## 1. Disponibilità dell'API

- **SLI**: richieste a `/api/v1/*` con stato diverso da 5xx / tutte le richieste a `/api/v1/*`. Fonte: le righe `academy_hub.richieste` dei log JSON dell'App (`stato`, `rotta`; fase 12, `osservabilita.py`), più il test di fumo di ogni rilascio (`scripts/fumo_rilascio.py`).
- **SLO**: 99% su 30 giorni. Budget di errore: 1% delle richieste (con il traffico del prototipo, poche decine al giorno, basta una mattina di 500 per bruciarlo).
- **Misura**: log dell'App (Compute → Apps → academy-hub-prod → Logs), contando le righe con `"logger": "academy_hub.richieste"` per `stato`.
- **Limite noto**: le richieste respinte dal proxy di Databricks Apps (App ferma, 502) non arrivano all'App e non finiscono nei suoi log: quelle le vede solo il fumo del rilascio.

## 2. Freschezza dei report

- **SLI**: ore trascorse dall'ultimo esito `aggiornato` in `<catalogo>.qualita.esiti` (il gold dei report si riscrive solo con quell'esito, ADR-0017).
- **SLO**: meno di 26 ore nel 95% dei giorni (il job `analisi` gira alle 05:00; 2 ore di margine per ritentativi e coda del serverless).
- **Misura**:

  ```sql
  SELECT timestampdiff(HOUR, max(registrato_il), current_timestamp()) AS ore_dall_ultimo_aggiornamento
  FROM academy_prod.qualita.esiti
  WHERE esito = 'aggiornato'
  ```

- **Avvisi che lo proteggono**: email del job `analisi` a ogni run fallita, email della pipeline `storico` sugli aggiornamenti falliti, alert SQL `academy-qualita-<target>` alle 06:00 se nelle ultime 24 ore c'è un esito `bloccato` o `errore` (`databricks.yml`).
- **Limite noto**: se il job non parte affatto (schedule in pausa), nessun esito viene scritto e nessun avviso scatta; lo scopre solo la misura qui sopra.
