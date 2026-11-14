# Infrastruttura come codice

Terraform per la piattaforma, il bundle (`databricks.yml`) per le risorse del progetto: vedi [ADR-0012](../docs/adr/0012-infrastruttura-come-codice.md).

| Cartella | Provider | Workspace HCP | Che cosa |
|---|---|---|---|
| `github/` | `integrations/github` | `academy-github` | repository, ruleset `main protetto`, environment `infra` e `infra-plan`, label |

Lo stato è su HCP Terraform Free (organizzazione `academy-hub-studio`, execution mode locale). Il workflow `.github/workflows/infra.yml` fa il plan nelle PR, l'apply su `main` dopo l'approvazione nell'environment `infra` e un plan di deriva ogni lunedì.

## Dal PC

```bash
terraform login                      # una volta: token di HCP Terraform
cd infra/github
terraform init
GITHUB_TOKEN=$(gh auth token) terraform plan
```

## Prima volta (bootstrap)

1. Su HCP Terraform: organizzazione `academy-hub-studio`, con execution mode di difetto **Local** (Settings → General). I workspace nascono al primo `terraform init`.
2. Token: uno di HCP (User Settings → Tokens) e due fine-grained di GitHub limitati a questo repository, con scadenza:
   - lettura: *Administration*, *Environments*, *Metadata*, *Issues*, *Secrets*, *Variables* in sola lettura;
   - scrittura: gli stessi permessi in lettura e scrittura.
3. Dal PC, `terraform apply` in `infra/github/`: importa ciò che esiste e crea gli environment `infra` e `infra-plan`.
4. Secret negli environment (mai nei file):

   ```bash
   gh secret set TF_API_TOKEN --env infra-plan
   gh secret set TF_API_TOKEN --env infra
   gh secret set GH_TERRAFORM_LETTURA --env infra-plan
   gh secret set GH_TERRAFORM_SCRITTURA --env infra
   ```

Da lì ogni modifica passa da una PR.
