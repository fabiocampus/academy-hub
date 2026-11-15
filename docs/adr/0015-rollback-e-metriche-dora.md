# ADR-0015 · Rollback dell'artifact e metriche DORA dai deployment

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 10 (issue #81, #88). Il rilascio continuo (ADR-0013) porta ogni merge su `main` in collaudo e, dopo l'approvazione, in produzione. Servono due cose ancora:

- tornare in fretta a una versione precedente quando un rilascio va male, senza aspettare un revert, una CI e una build nuova;
- misurare il processo con le quattro metriche DORA (frequenza dei rilasci, lead time for changes, change failure rate, tempo di ripristino) senza un servizio esterno.

Vincoli: un solo artifact per rilascio, conservato 90 giorni (ADR-0013 §4); migrazioni solo in avanti e compatibili con la versione precedente (ADR-0013 §7); environment `collaudo` e `prod` ammessi solo dal ramo `main`; Free plan di GitHub, repository pubblico.

## Decisione

1. **Rollback = rilasciare di nuovo un artifact già rilasciato.** Workflow `rollback.yml`, solo `workflow_dispatch`, con l'id della run di `rilascio.yml` da ripristinare. Niente nuova build: lo stesso artifact (`app-<sha>`) già provato in collaudo e in produzione.
2. **Verifica della run prima di tutto** (job `verifica`): workflow `rilascio.yml`, ramo `main`, job `prod / rilascia` riuscito, artifact ancora disponibile. Si torna solo a una versione che è già stata in produzione.
3. **Stesso percorso del rilascio.** `rollback.yml` richiama `rilascia-ambiente.yml` per collaudo e poi per prod, con l'approvazione dell'environment `prod` e la stessa concurrency per ambiente: un rollback non si sovrappone a un rilascio. Due input nuovi del workflow riusabile: `run_id` (l'artifact si scarica da quella run, serve `actions: read`) e `rilascio` (lo SHA atteso in `build/app/RILASCIO`).
4. **Bundle e fumo del commit ripristinato.** Il checkout è dello SHA dell'artifact, non di `main`: `databricks.yml` (variabili, flag, risorse) e `fumo_rilascio.py` sono quelli di quella versione, che sanno rilasciarla e controllarla. Il workflow riusabile resta quello di `main`: un cambio della sua interfaccia con lo script di fumo deve restare compatibile con i rilasci degli ultimi 90 giorni.
5. **Il database non torna indietro.** L'App vecchia parte su uno schema già migrato: per questo le migrazioni sono expand/contract (ADR-0013 §7). Un rollback oltre una migrazione che non è compatibile all'indietro non si fa: si corregge in avanti.
6. **Tornare avanti** è un altro rollback con la run del rilascio più recente, oppure "Run workflow" di `rilascio.yml` (nuova build di `main`).
7. **Metriche DORA dai deployment di GitHub.** Ogni job con `environment:` registra un deployment con i suoi stati e il link alla run. `scripts/dora.py` li legge con l'API REST e calcola le metriche per un environment (di difetto `prod`) in un periodo; un deployment è un rollback se la sua run è di `rollback.yml`. Definizioni in `docs/dora.md`. L'istantanea si scrive in `docs/dora.md` con `--aggiorna` e si committa: è il resoconto, non un cruscotto.

## Alternative scartate

- **Revert su `main`**: ci vogliono PR, CI e build (decine di minuti) e il codice rilasciato non è quello già provato. Resta la correzione definitiva, dopo il rollback.
- **Input `run_id` dentro `rilascio.yml`**: un solo workflow con due percorsi (build o ripristino) e condizioni su ogni job. Un file separato si legge meglio e nei deployment si riconosce dal percorso della run.
- **Strumento DORA esterno** (Four Keys, Sleuth, servizi a pagamento): un servizio in più da tenere per un progetto con un solo sviluppatore; i dati sono già nei deployment.

## Conseguenze

- Il ripristino richiede solo l'id di una run e l'approvazione di prod: pochi minuti, il tempo di deploy e avvio dell'App.
- Il rollback ha un limite di 90 giorni (artifact scaduti) e di migrazioni (punto 5).
- Un deployment di rollback ha come commit quello di `main` della run di rollback, non quello ripristinato: lo SHA ripristinato è nel titolo della run e in `/health`.
- Le metriche sono grezze con pochi rilasci e un periodo lungo; il change failure rate conta come fallimento un rilascio seguito da un rollback, anche quello di una prova.
