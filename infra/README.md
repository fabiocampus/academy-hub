# Infrastruttura come codice

Terraform per la piattaforma, il bundle (`databricks.yml`) per le risorse del progetto: vedi [ADR-0012](../docs/adr/0012-infrastruttura-come-codice.md).

| Cartella | Provider | Workspace HCP | Che cosa |
|---|---|---|---|
| `github/` | `integrations/github` | `academy-github` | repository, ruleset `main protetto`, environment `infra` e `infra-plan` (Terraform) e `collaudo` e `prod` (rilascio, ADR-0013), label |
| `databricks/` | `databricks/databricks` | `academy-databricks` | cataloghi `academy_collaudo`/`academy_prod` (in SQL, `crea_catalogo.py`), schemi `bronze`/`silver`/`gold`, grant, secret scope `academy-hub`; database di Lakebase registrato in Unity Catalog (`academy_<env>_oltp`) e grant di `academy-rilascio` per il job `analisi` (`analisi.tf`, `carica_schemi.py`, ADR-0016); l'apply va fatto prima del rilascio che porta il job |
| `databricks-identita/` | `databricks`, `github`, `time` | `academy-databricks-identita` | service principal `academy-terraform` (admin del workspace, `CREATE CATALOG`) e `academy-rilascio` (admin del workspace, deploy del bundle, ADR-0013), i loro secret OAuth e i secret `DATABRICKS_*` (e `ACADEMY_ADMIN_EMAIL`) negli environment. **Solo dal PC**, niente workflow |

Lo stato è su HCP Terraform Free (organizzazione `academy-hub-studio`, execution mode locale). Il workflow `.github/workflows/infra.yml` fa il plan nelle PR, l'apply su `main` dopo l'approvazione nell'environment `infra` e un plan di deriva ogni lunedì, per `github/` e `databricks/`.

## Dal PC

```bash
terraform login                      # una volta: token di HCP Terraform
cd infra/github
terraform init
GITHUB_TOKEN=$(gh auth token) terraform plan

cd ../databricks                     # e ../databricks-identita
DATABRICKS_CONFIG_PROFILE=academy GITHUB_TOKEN=$(gh auth token) terraform plan
```

Su Windows il provider databricks cerca la CLI per l'autenticazione del profilo: se non la trova, `DATABRICKS_CLI_PATH` con il percorso di `databricks.exe`. Per creare un catalogo servono anche `python` (non l'alias dello Store) e `databricks` nel PATH: `crea_catalogo.py` gira con `cmd /C`.

`databricks-identita/` si applica solo dal PC: il secret di un service principal si legge con un'API di account, e su Free Edition admin dell'account è solo il proprietario. Lì va rifatto un `apply` quando il plan propone di sostituire i secret (dopo 335 giorni; scadono dopo un anno).

## Prima volta (bootstrap)

1. Su HCP Terraform: organizzazione `academy-hub-studio`, con execution mode di difetto **Local** (Settings → General). I workspace nascono al primo `terraform init`.
2. Token: uno di HCP (User Settings → Tokens) e due fine-grained di GitHub limitati a questo repository, con scadenza:
   - lettura: *Administration*, *Environments*, *Issues*, *Metadata* in sola lettura;
   - scrittura: gli stessi permessi in lettura e scrittura (*Metadata* resta in lettura).

   *Secrets* e *Variables* si aggiungono quando Terraform comincerà a gestirli (PR B della fase 9).
3. Dal PC, `terraform apply` in `infra/github/`: importa ciò che esiste (anche `infra-plan`, creato dalla prima esecuzione del workflow) e crea l'environment `infra` con approvatore e policy sul ramo `main`.

   Prima di questo passo nessun push su `main` deve toccare `infra/`: il job di apply farebbe nascere `infra` senza approvatore.
4. Secret negli environment (mai nei file):

   ```bash
   gh secret set TF_API_TOKEN --env infra-plan
   gh secret set TF_API_TOKEN --env infra
   gh secret set GH_TERRAFORM_LETTURA --env infra-plan
   gh secret set GH_TERRAFORM_SCRITTURA --env infra
   ```

5. Databricks (fase 9, PR B), dal PC con il profilo `academy`:
   1. `databricks-identita/`: `apply` (service principal, grant `CREATE CATALOG`, secret e secret `DATABRICKS_*` negli environment);
   2. `databricks/`: `apply` (cataloghi, schemi, grant, secret scope). Su un workspace dove esistono già, senza stato, prima `terraform import` di schemi (`<catalogo>.<schema>`) e grant (`catalog/<catalogo>`, `schema/<catalogo>.gold`).

   Se cataloghi e schemi stanno ancora nel bundle, prima `databricks bundle deployment unbind <chiave> -t <target>` per `academy`, `bronze`, `silver`, `gold`, con il `databricks.yml` che li contiene: un `bundle deploy` che non li trova più nel file li cancellerebbe.

6. Rilascio continuo (fase 10, ADR-0013), dal PC:
   1. `github/`: `apply` (environment `collaudo` e `prod`);
   2. `databricks-identita/`: `apply` (service principal `academy-rilascio` e i suoi secret in `collaudo` e `prod`);
   3. migrazione del bundle dallo stato dell'utente a quello del service principal, con le sue credenziali (dallo stato, senza stamparle) e un file di configurazione della CLI vuoto, così la CLI non usa il profilo dell'utente. Prima si sposta la cache locale `.databricks/` (ignorata da Git): contiene lo stato dei deploy fatti come utente, e la CLI la preferirebbe allo stato, vuoto, del service principal («Resource already managed»):

      ```bash
      export DATABRICKS_CONFIG_FILE=$(mktemp) DATABRICKS_HOST=... DATABRICKS_CLIENT_ID=... DATABRICKS_CLIENT_SECRET=...
      export BUNDLE_VAR_admin_email=... BUNDLE_VAR_rilascio=$(python scripts/prepara_app.py >/dev/null && cat build/app/RILASCIO)
      mv .databricks /altrove
      databricks bundle deployment bind postgres_projects.academy_hub projects/academy-hub -t prod --auto-approve
      databricks bundle deployment bind postgres_endpoints.production projects/academy-hub/branches/production/endpoints/primary -t prod --auto-approve
      databricks bundle deployment bind apps.academy_hub academy-hub-prod -t prod --auto-approve
      databricks bundle deployment bind postgres_branches.collaudo projects/academy-hub/branches/collaudo -t collaudo --auto-approve
      databricks bundle deployment bind postgres_endpoints.collaudo projects/academy-hub/branches/collaudo/endpoints/primary -t collaudo --auto-approve
      databricks bundle deployment bind apps.academy_hub academy-hub-collaudo -t collaudo --auto-approve
      databricks bundle plan -t prod && databricks bundle plan -t collaudo   # 0 to add, 0 to delete
      ```

      Le chiavi sono qualificate dal tipo: `academy_hub` e `collaudo` stanno in due tipi ciascuna. Poi un deploy di collaudo con `bundle run` e `scripts/fumo_rilascio.py`; infine si sposta di nuovo `.databricks/` e si cancella `/Workspace/Users/<email>/.bundle/academy-hub` (lo stato dell'utente con i file: le App non lo usano più). Fatto il 2026-11-15.

Da lì ogni modifica passa da una PR (tranne `databricks-identita/`).
