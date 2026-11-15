# Retrospettiva: sviluppo con un agente

Il progetto (fasi 1–13, 2026-11-13 → 2026-11-15) è stato scritto quasi tutto da Claude Code, con l'utente che decideva perimetro e design, approvava merge e rilasci in produzione. Qui che cosa ha funzionato, dove l'agente ha sbagliato e quali regole sono nate dagli errori. I numeri sono issue e PR del repository.

## Che cosa ha fatto bene

- **Volume con disciplina.** API a livelli, frontend, parte analitica, Terraform e pipeline di rilascio in tre giorni, ogni modifica da una PR collegata a una issue e con CI verde (oltre 600 test pytest, un centinaio di Vitest, end-to-end con Playwright e axe).
- **Test dove contano.** Concorrenza sull'ultimo posto con transazioni vere (ADR-0004), matrice rotta × profilo che fallisce se una rotta non ha la sua riga, contratto OpenAPI con impronta per versione.
- **Misurare invece di supporre.** `EXPLAIN ANALYZE` su dati sintetici: la query delle richieste da decidere (US-07) riscritta da 150 a 15 ms (#54). Terraform introdotto con 28 `import` e piano a zero modifiche (#77); deriva provata aggiungendo un grant a mano (#79); rollback provato andando indietro e avanti in collaudo e produzione (#89).
- **Gli end-to-end hanno trovato bug veri** che i test unitari non vedevano: callback di `mutate()` perse allo smontaggio del componente e contrasto insufficiente del tema Mantine (#67).
- **Incidente gestito con metodo**: alert, rollback, correzione, post-mortem con azioni (#114, #115).

## Dove ha sbagliato

### Logica plausibile ma sbagliata

Codice che sembrava giusto, passava i test locali e falliva nel sistema vero:

| Caso | Che cosa è successo | Trovato da |
|---|---|---|
| `SystemExit(0)` in un task serverless | Su Databricks il task gira in IPython: qualsiasi `SystemExit` lo fa fallire (#97) | prima run in collaudo |
| Primo snapshot vuoto | In produzione, tabelle vuote → `FIRST_SNAPSHOT_EMPTY` nella pipeline SCD 2 (#99) | job di produzione |
| `spark.catalog.tableExists` | Non ammesso da py4j nella pipeline serverless (#101) | job di collaudo |
| Tabella che può non esistere | `gold` leggeva `qualita.verdetti` prima che qualcuno la creasse (#104) | revisore |
| Secret del workflow riutilizzabile | Il workflow chiamato riceveva secret vuoti: mancava `secrets: inherit` (#84) | primo rilascio |
| Identità provvisoria | Con `ACADEMY_AMBIENTE` predefinito a `locale` l'header di test `X-Persona-Id` passava anche fuori dal locale (#58) | rilettura della sicurezza |
| Orologio dell'App | Momenti di approvazione presi dall'orologio dell'App e non da quello del database; controllo del titolare dopo i lock (#51) | revisore |
| Un errore ferma tutto | Il job di sistema si fermava alla prima edizione in errore invece di isolarla (#52) | revisore |
| `on_failure` del job | Con un task finale `ALL_DONE` il job finisce `SUCCESS_WITH_FAILURES` e l'email del job non parte (#114) | incidente simulato |

Il filo comune: **l'agente conosce l'API documentata, non il comportamento della piattaforma gratuita** (Databricks serverless, Free Edition). Quei casi si scoprono solo eseguendo nel sistema vero.

### Test che non verificano abbastanza

Non è stato trovato un test vuoto in `main`, ma il rischio è stato reale durante il lavoro:

- test che controllavano solo lo stato HTTP e non il corpo né il database; il revisore li ha fatti rafforzare in più PR (#51, #52);
- una matrice che gira su tutte le rotte con le feature flag spente avrebbe visto 404 ovunque e provato poco: le flag vanno accese nei test (#87);
- mutazioni manuali del codice per vedere se i test se ne accorgono: utili, ma una volta il ripristino con `git checkout --` ha perso modifiche non salvate.

### Dipendenze

Nessuna dipendenza inventata è arrivata in un lock: le versioni sono state verificate sul registro e fissate (`uv.lock`, `package-lock.json`, action per SHA, immagini `tag@digest`). Errori vicini: pacchetti con nomi poco ovvi (`httpx2` per il client di test di Starlette) e proposte di Dependabot in conflitto con le scelte dell'ADR-0001 (Python 3.15, PostgreSQL 18), bloccate con regole di ignore (#48).

### Errori di processo dell'agente

- Azioni su PR non proprie (aggiornare il branch di una PR di Dependabot) senza chiedere: rifiutate dall'utente.
- Problemi di Windows ripetuti: codifica cp1252 al posto di UTF-8 (testo rovinato), fine riga CRLF, percorsi convertiti da Git Bash.
- Una nota di memoria sovrascritta con un contenuto segnaposto.

## Regole aggiunte per prevenirlo

| Errore | Regola | Dove |
|---|---|---|
| Comportamenti della piattaforma | Ogni modifica va in collaudo ed esegue il job prima della produzione; *Lezioni imparate* elenca i casi già visti | `rilascio.yml`, `CLAUDE.md` |
| Schema nominato dal bundle ma non creato | Test che lega gli schemi del bundle a Terraform | `backend/tests/test_bundle_schemi.py` |
| Colonna tolta ma letta dall'analisi | Test che lega `tabelle.py` ai modelli SQLAlchemy | `backend/tests/test_contratto_analisi.py` |
| Rotta senza controllo dei permessi | Una riga per rotta, o la matrice fallisce | `backend/tests/test_autorizzazione.py` |
| API cambiata senza versione | Impronta del contratto per versione | `backend/tests/test_contratto.py` |
| Passi dimenticati nei compiti ripetuti | Skill `nuova-migrazione` e `nuova-rotta` | `.claude/skills/`, ADR-0019 |
| Logica plausibile, test deboli | Subagent `revisore` prima di ogni merge; test di stato **e** di effetto | `.claude/agents/revisore.md`, `CONTRIBUTING.md` |
| Errori trovati tardi | Hook con ruff e test veloci dopo ogni modifica a un `.py` | `.claude/hooks/dopo_modifica.py` |
| Azioni irreversibili | `git push`, `gh pr merge`, `gh api`, `terraform apply`, `databricks` chiedono conferma; `push --force`, `reset --hard`, `clean` vietati; ruleset su `main` senza eccezioni; approvazione umana di `prod` | `.claude/settings.json`, `infra/github/` |
| Segreti e dati reali in un repository pubblico | gitleaks in pre-commit e in CI, push protection, solo dati sintetici | `.pre-commit-config.yaml`, `ci.yml` |

## Che cosa rifarei diverso

- Provare **subito** un job minimo sulla piattaforma vera (Databricks serverless) prima di scrivere la logica: metà degli errori della tabella sopra sarebbero emersi il primo giorno.
- Scrivere le skill dei compiti ripetuti alla seconda ripetizione, non alla fine.
- Tenere le lezioni in `CLAUDE.md` man mano, invece che nelle note di passaggio fra sessioni.
