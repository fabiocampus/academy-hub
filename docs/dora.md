# Metriche DORA

Le quattro metriche DORA del rilascio continuo (ADR-0013), calcolate da `scripts/dora.py` dai deployment che GitHub registra negli environment (ADR-0015).

```bash
python scripts/dora.py                          # markdown su stdout: environment prod, ultimi 90 giorni
python scripts/dora.py --environment collaudo --giorni 30
python scripts/dora.py --aggiorna docs/dora.md  # riscrive l'istantanea qui sotto
```

Il token viene da `GH_TOKEN` o `GITHUB_TOKEN`, altrimenti da `gh auth token`; senza, l'API pubblica concede 60 richieste l'ora.

## Dati

Ogni job con `environment:` (`rilascia-ambiente.yml`) crea un deployment nell'environment, con lo SHA della run e una sequenza di stati: `waiting` (approvazione), `queued`, `in_progress`, poi `success`, `failure` o `error`. `inactive`, se compare, si ignora.

- Conta solo un deployment con uno stato finale (`success`, `failure`, `error`); la sua ora è quella dello stato finale. Uno ancora in attesa non conta; un rifiuto all'approvazione o un annullamento conta solo se GitHub lo registra come `failure` o `error` (da verificare alla prima occasione).
- È un **rollback** se la run collegata (`log_url`) è di `rollback.yml`, altrimenti è un **rilascio**.

## Definizioni

| Metrica | Come si calcola |
| --- | --- |
| Frequenza dei rilasci | Rilasci riusciti nel periodo, divisi per le settimane del periodo. I rollback non contano. |
| Lead time for changes | Per ogni rilascio riuscito, i commit fra il rilascio riuscito precedente e il suo SHA (`compare`); per ognuno, dall'ora del commit su `main` (committer date: con lo squash merge è il merge della PR) alla fine del rilascio. Mediana. Comprende CI, build, collaudo e attesa dell'approvazione. Del primo rilascio della storia conta solo il suo commit. |
| Change failure rate | Rilasci falliti, più quelli riusciti e seguiti subito da un rollback, sul totale dei rilasci del periodo. |
| Tempo di ripristino | Da un rilascio fallito (o riuscito e poi annullato) al primo deployment riuscito che lo segue, rilascio o rollback. Più guasti di fila contano una volta, dal primo. Mediana. |

## Limiti

- Un difetto corretto in avanti (con una PR, senza rollback) non si vede: il rilascio difettoso resta "riuscito". Servirebbe collegare le issue di tipo bug ai rilasci.
- Un fallimento del solo test di fumo, con l'App già aggiornata, è un `failure` come un deploy non riuscito.
- Con pochi rilasci e un periodo di 90 giorni la frequenza è bassa per costruzione: il progetto ha pochi giorni.
- "Annullato" vuol dire seguito subito da un rollback: con R2 riuscito, R3 fallito e un rollback a R1, R2 non risulta annullato.
- Il lead time di un rilascio legge al massimo 250 commit (limite di `compare`). Un rilascio di uno SHA più vecchio dell'ultimo (approvazioni in ordine inverso) non porta commit nuovi.
- Il rollback di prova della fase 10 conta come un fallimento del rilascio che ha annullato.

## Prova del rollback (fase 10)

Il 2026-11-15, dopo il rilascio di 1c774ea (run 43717943683):

1. `rollback.yml` con la run 43711400013 (run 43718710085): stesso artifact di a8f5b4f, checkout di a8f5b4f, fumo in collaudo e in prod con `/health` = a8f5b4f.
2. `rollback.yml` con la run 43717943683 (run 43718950203): di nuovo 1c774ea in entrambi gli ambienti, fumo verde.

Nessuna migrazione fra le due versioni. Tempo di ripristino misurato in prod (dal rilascio annullato al rollback riuscito, approvazione compresa): 3 minuti.

## Istantanea

<!-- dora:inizio -->
Environment `prod` di `fabiocampus/academy-hub`, deployment finiti fra il 2026-08-17 13:29 UTC e il 2026-11-15 13:29 UTC.

| Metrica | Valore | Base |
| --- | --- | --- |
| Frequenza dei rilasci | 0.2 a settimana | 3 rilasci riusciti |
| Lead time for changes (mediana) | 8 min | 3 commit |
| Change failure rate | 33% | 1 falliti o annullati su 3 rilasci |
| Tempo di ripristino (mediana) | 3 min | 1 ripristini, 2 rollback |

| Fine | Tipo | Esito | Commit della run |
| --- | --- | --- | --- |
| 2026-11-15 12:06 UTC | rilascio | riuscito | `a8f5b4f` |
| 2026-11-15 12:57 UTC | rilascio | riuscito | `9d76b45` |
| 2026-11-15 13:22 UTC | rilascio | riuscito, poi annullato | `1c774ea` |
| 2026-11-15 13:25 UTC | rollback | riuscito | `1c774ea` |
| 2026-11-15 13:28 UTC | rollback | riuscito | `1c774ea` |
<!-- dora:fine -->
