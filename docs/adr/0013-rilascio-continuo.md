# ADR-0013 · Rilascio continuo: un artifact, due ambienti, un service principal

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 10: una modifica approvata in PR deve arrivare in produzione senza passaggi manuali oltre all'approvazione. Fino alla fase 9 il bundle si rilasciava dal PC, con l'utente come identità: App, progetto Lakebase e stato del bundle stavano nella sua cartella (`/Workspace/Users/<email>/.bundle/academy-hub/<target>`).

Vincoli:

- Free Edition non ha l'account console, quindi niente federation OIDC fra GitHub Actions e Databricks (ADR-0012): l'identità del workflow è un service principal con un secret OAuth M2M, come `academy-terraform`.
- Un solo workspace (ADR-0002) e un solo progetto Lakebase: il branch `collaudo` vive nel progetto di prod (ADR-0010).
- Il repository è pubblico, e così i log dei workflow.

## Decisione

1. **Un service principal per il rilascio, `academy-rilascio`**, separato da `academy-terraform` (chi rilascia il progetto non gestisce la piattaforma, e viceversa) ma unico per collaudo e prod. Uno per ambiente non separerebbe davvero niente: il progetto Lakebase è uno, e il service principal di collaudo dovrebbe comunque gestire il progetto in cui vive prod. È admin del workspace: App e progetti Lakebase danno `CAN_MANAGE` al gruppo `admins`, e il bundle assegna i permessi delle risorse delle App. Nasce in `infra/databricks-identita/` (solo dal PC, ADR-0012 §5), con il secret che ruota dopo 335 giorni e scrive negli environment `collaudo` e `prod` `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` e `ACADEMY_ADMIN_EMAIL` (letta da `databricks_current_user`: chi applica dal PC è l'amministratore dell'App; mai nel repository).
2. **Environment di GitHub** in `infra/github/`: `collaudo` e `prod`, entrambi solo dal ramo `main`; `prod` con approvatore e senza bypass degli admin.
3. **Workflow `rilascio.yml`** su ogni push a `main`: `ci.yml` richiamato (`workflow_call`; su `main` non parte più da solo), `build`, `collaudo`, `prod`. Il deploy di un ambiente è un workflow riusabile, `rilascia-ambiente.yml`: deploy del bundle, `bundle run` dell'App, test di fumo. Il job di prod aspetta collaudo verde e l'approvazione. Un rilascio alla volta per ambiente, mai interrotto a metà: il gruppo di concurrency è nel job di `rilascia-ambiente.yml` (`rilascio-<environment>`, `cancel-in-progress: false`), non nel workflow, così un prod in attesa di approvazione non blocca il collaudo dei push successivi. GitHub tiene in coda un solo job per gruppo: se ne arriva un altro, quello in coda (non quello in corso) si annulla e vince il più recente. `workflow_dispatch` rilancia a mano l'ultimo `main`.
4. **Un solo artifact.** `build` esegue `scripts/prepara_app.py` una volta e carica `build/app` come artifact `app-<sha>` (90 giorni). Collaudo e prod scaricano lo stesso artifact; fra gli ambienti cambiano solo target del bundle, variabili e secret. Il commit sta nell'artifact (`build/app/RILASCIO`), il bundle lo passa all'App (`ACADEMY_RILASCIO`) e `/health` lo mostra.
5. **Test di fumo** (`scripts/fumo_rilascio.py`): con il token M2M del service principal, attraverso il proxy delle App, controlla che `/health` riporti l'ambiente e lo SHA dell'artifact (riprova per cinque minuti mentre l'App si riavvia), che configurazione dell'API e frontend rispondano e che senza token il proxy rifiuti. Solo letture: in prod nessun dato di prova.
6. **Migrazione dello stato del bundle.** App, progetto, branch ed endpoint esistenti passano allo stato del service principal con `databricks bundle deployment bind`, senza ricrearli: restano URL, service principal delle App (proprietari degli schemi Postgres) e dati. Poi si cancella la copia del bundle dell'utente, stato compreso (procedura in `infra/README.md`, bootstrap 6). Da allora il bundle si rilascia solo come service principal: un deploy con il proprio utente creerebbe un secondo stato, che tenterebbe di creare risorse già esistenti.
7. **Migrazioni del database solo in avanti e compatibili con la versione precedente** (expand/contract): l'App le applica all'avvio (ADR-0010), e un rollback rilascia l'artifact precedente su uno schema già migrato. Una colonna si toglie in un rilascio successivo a quello che smette di usarla.
8. **Log pubblici.** Host e credenziali sono secret, quindi GitHub li maschera; l'URL dell'App (contiene l'id del workspace) si maschera prima del deploy. `bundle deploy` è senza `--auto-approve`: se volesse cancellare o ricreare una risorsa si ferma.

## Conseguenze

- Il merge di una PR porta la build in collaudo da solo, e in produzione dopo un clic sull'approvazione. La CI gira anche su `main`, prima del rilascio.
- Un secret in più da rinnovare dal PC, insieme a quello di `academy-terraform` (#80).
- Il service principal admin può fare tutto nel workspace: rischio accettato, come per `academy-terraform` (dati sintetici, un solo sviluppatore). Con un account vero: federation OIDC al posto del secret, e due workspace con un service principal ciascuno.
- Da questa fase il rollback (rilascio di un artifact precedente) e la feature flag del calendario sono nella seconda PR; le metriche DORA si calcolano dai deployment che gli environment registrano.
