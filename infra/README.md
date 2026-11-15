# Infrastruttura come codice

Terraform per la piattaforma, il bundle (`databricks.yml`) per le risorse del progetto: vedi [ADR-0012](../docs/adr/0012-infrastruttura-come-codice.md).

| Cartella | Provider | Workspace HCP | Che cosa |
|---|---|---|---|
| `github/` | `integrations/github` | `academy-github` | repository, ruleset `main protetto`, environment `infra` e `infra-plan`, label |
| `databricks/` | `databricks/databricks` | `academy-databricks` | cataloghi `academy_collaudo`/`academy_prod` (in SQL, `crea_catalogo.py`), schemi `bronze`/`silver`/`gold`, grant, secret scope `academy-hub` |
| `databricks-identita/` | `databricks`, `github`, `time` | `academy-databricks-identita` | service principal `academy-terraform` (admin del workspace, `CREATE CATALOG`), il suo secret OAuth e i secret `DATABRICKS_*` negli environment. **Solo dal PC**, niente workflow |

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

Su Windows il provider databricks cerca la CLI per l'autenticazione del profilo: se non la trova, `DATABRICKS_CLI_PATH` con il percorso di `databricks.exe`.

`databricks-identita/` si applica solo dal PC: il secret di un service principal si legge con un'API di account, e su Free Edition admin dell'account è solo il proprietario. Lì va rifatto un `apply` quando il plan propone di sostituire il secret (dopo 335 giorni; scade dopo un anno).

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
   2. `databricks/`: `apply` (cataloghi, schemi, grant, secret scope; gli esistenti con i blocchi `import`).

   Se cataloghi e schemi stanno ancora nel bundle, prima `databricks bundle deployment unbind <chiave> -t <target>` per `academy`, `bronze`, `silver`, `gold`, con il `databricks.yml` che li contiene: un `bundle deploy` che non li trova più nel file li cancellerebbe.

Da lì ogni modifica passa da una PR (tranne `databricks-identita/`).
