# ADR-0003 · GitHub al posto di Azure DevOps, con repository pubblico

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Il corso usa Azure DevOps: Boards, Repos, Pipelines. Il prototipo ha il vincolo di costo zero e **nessuna carta di credito**. Alla creazione dell'organizzazione Azure DevOps è stata richiesta una carta, quindi la piattaforma non è utilizzabile.

GitHub Free non chiede una carta, ma limita alcune funzioni ai repository pubblici:

| Funzione | Repository pubblico | Repository privato (Free) |
|---|---|---|
| Ruleset e branch protection | sì | no |
| Environment con approvatori obbligatori | sì | no |
| Secret di environment | sì | no |
| Minuti di GitHub Actions | illimitati | limitati |

## Decisione

- Il ciclo di sviluppo usa **GitHub**: Issues e Projects per il backlog, il repository GitHub, GitHub Actions con runner ospitati per CI/CD.
- Il repository è **pubblico**.
- Il rilascio su Databricks si autentica con **OIDC di GitHub Actions** (workload identity federation) se Free Edition permette di configurare la federation policy; altrimenti con il segreto OAuth di un service principal o un token a scadenza breve in un secret di environment.

Corrispondenze con il corso:

| Azure DevOps | GitHub |
|---|---|
| Boards: epic, feature, user story | Issues con label `type:*` e sub-issue; board in Projects |
| Branch policy | Ruleset su `main` |
| Build validation | Status check obbligatori |
| Pipeline a stage | Workflow con job concatenati |
| Environment con approvazione | Environment con required reviewers |
| Variable group segreto | Secret di repository e di environment |
| Provider Terraform `azuredevops` | Provider Terraform `github` |

## Conseguenze

- **Positive:** costo zero senza carta; runner ospitati, quindi le pipeline non dipendono dal PC acceso; secret scanning con push protection, Dependabot e code scanning gratuiti sui repository pubblici; la federazione OIDC è più semplice che con Azure DevOps.
- **Negative:**
  - tutto ciò che si committa è pubblico: servono solo dati sintetici, Gitleaks in pre-commit e in CI, secret scanning con push protection;
  - i workflow avviati da pull request di fork non devono mai ricevere segreti: si usa `pull_request`, non `pull_request_target` con il checkout del codice della PR;
  - lavorando da soli non si può approvare la propria PR: il ruleset chiede 0 approvazioni e la revisione è affidata al subagent revisore e alla rilettura personale;
  - il modulo 12 del corso (Azure Pipelines) si esercita con GitHub Actions; la sintassi cambia, il modello (stage, approvazioni, promozione della stessa build) resta uguale.
- **Da rivalutare:** se in futuro si aggiunge un account Azure, la fase 14 confronta la stessa CI su Azure Pipelines.

## Alternative considerate

- **Azure DevOps con carta:** escluso dal vincolo di progetto.
- **Repository GitHub privato:** si perderebbero ruleset, environment con approvatori e minuti illimitati; le protezioni diventerebbero convenzioni non applicate.
- **GitLab Free:** ruleset ed environment protetti hanno limiti simili; l'ecosistema GitHub è più vicino a quello del corso e degli strumenti di Claude Code.
