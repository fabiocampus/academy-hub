# ADR-0012 · Infrastruttura come codice: Terraform per la piattaforma, bundle per il progetto

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

Fase 9: le impostazioni della piattaforma devono stare nel codice e poter essere ricreate da zero. Finora sono state fatte a mano o con la CLI: impostazioni del repository, ruleset `main protetto`, label, e su Databricks (fase 8) cataloghi, schemi e grant dentro il bundle.

Vincoli:

- Tutto gratuito, senza carta di credito. HCP Terraform Free (piano in vigore dal 31 marzo 2026) dà utenti illimitati, 500 risorse gestite e una run alla volta: qui le risorse sono qualche decina.
- I runner ospitati di GitHub devono raggiungere lo stato, quindi un PostgreSQL sul PC non va bene.
- Il repository è pubblico: niente credenziali nei file, e lo stato (che può contenere valori sensibili) non sta nel repository.
- Free Edition: l'API non crea cataloghi (ADR-0011); service principal e OAuth M2M invece funzionano (sonda del 2026-11-14), mentre la federation OIDC si configura dall'account console, che qui non c'è.

## Decisione

1. **Confine.** Terraform gestisce la piattaforma: repository GitHub, ruleset, environment e label (`infra/github/`), e dalla seconda PR i secret e le variabili di environment che nascono da altre risorse (punto 5); cataloghi, schemi, grant e secret scope di Unity Catalog (`infra/databricks/`, seconda PR della fase). Il bundle gestisce le risorse del progetto, che cambiano con il codice: App, Lakebase, job, pipeline. Una risorsa ha un solo gestore. Quelle che già esistono entrano in Terraform con blocchi `import` nel codice, così il primo `plan` dimostra che codice e piattaforma coincidono.
2. **Stato su HCP Terraform Free**, organizzazione `academy-hub-studio`, un workspace per cartella (`academy-github`, `academy-databricks`), con execution mode **locale**: `plan` e `apply` girano sul PC o sul runner, HCP tiene solo lo stato (cifrato, con lock e storico delle versioni). Le credenziali dei provider non arrivano mai a HCP.
3. **Workflow `infra.yml`.** Su una PR che tocca `infra/**`: `fmt`, `validate`, `plan`, con il plan in un commento della PR (aggiornato a ogni push). Dopo il merge su `main`: un job nell'environment `infra`, che parte solo con l'approvazione e solo da un ramo protetto, rifà il plan e applica quel plan. Si approva guardando il plan della PR: quello applicato può differire se nel frattempo c'è stata deriva o un'altra PR, ed è nel log del job prima dell'apply. Ogni lunedì un plan con `-detailed-exitcode` fallisce se trova deriva. Una sola esecuzione alla volta, mai interrotta a metà.
4. **Due environment, due livelli di credenziali.** `infra-plan` (nessuna approvazione) ha un token GitHub di sola lettura; `infra` (approvazione, solo `main`) ha il token che scrive. Il token di HCP sta in entrambi ed è un token utente (il piano Free non ha team con permessi ridotti): da `infra-plan` può anche scrivere lo stato, rischio accettato perché solo il proprietario apre rami in questo repository. La policy dell'environment `infra` ammette solo il ramo `main` per nome, non «i rami protetti»: `main` è protetto da un ruleset, e senza branch protection classiche GitHub farebbe entrare ogni ramo. Le PR da fork e quelle di Dependabot non vedono i secret e fanno solo `fmt` e `validate`. Mai `pull_request_target`. Col token di sola lettura GitHub non restituisce le impostazioni di merge del repository: Terraform le ignora dopo la creazione (`ignore_changes`) invece di dare al plan un token che scrive; lo squash obbligatorio resta nel ruleset.
5. **I secret che fanno partire Terraform si mettono a mano** (`TF_API_TOKEN`, `GH_TERRAFORM_LETTURA`, `GH_TERRAFORM_SCRITTURA`), con `gh secret set --env`: Terraform non può gestire le credenziali con cui gira. I secret creati da Terraform stesso (seconda PR: il secret OAuth del service principal di Databricks verso l'environment di GitHub) passano da un provider all'altro senza che nessuno li veda.
6. **Il workflow dell'infrastruttura non è un check obbligatorio** del ruleset: parte solo se cambia `infra/`, e un check obbligatorio che non parte bloccherebbe ogni altra PR.
7. **Protezioni contro i danni.** Repository con `prevent_destroy` e `archive_on_destroy`; `prevent_destroy` anche su ruleset (ricrearlo lascerebbe `main` scoperto) ed environment `infra` (perderebbe secret e approvatore); label come risorse singole (`github_issue_label`), non come insieme autoritativo che cancellerebbe quelle create da Dependabot.

## Conseguenze

- Un cambio al ruleset, a una label o a un environment passa da una PR, come il codice; un cambio a mano dalla UI esce nel plan del lunedì.
- Per lavorare dal PC serve `terraform login` (token HCP) e `GITHUB_TOKEN=$(gh auth token)`; un `apply` dal PC resta possibile e scrive lo stesso stato con lo stesso lock.
- Il token GitHub che scrive (amministrazione del repository) è la credenziale più forte del progetto: sta solo nell'environment `infra`, che chiede l'approvazione. Un token fine-grained scade: rinnovarlo è un passo manuale.
- Se HCP Terraform Free cambiasse ancora, lo stato si sposta con `terraform init -migrate-state` verso un backend `pg` (per esempio su Lakebase).
