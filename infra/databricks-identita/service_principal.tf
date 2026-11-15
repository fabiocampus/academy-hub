# Identità del workflow infra.yml su Databricks (OAuth M2M), per infra/databricks.
# La stessa per plan e apply, in infra-plan e infra (ADR-0012). Admin del workspace:
# usa il warehouse e gestisce secret scope e permessi del workspace.

resource "databricks_service_principal" "terraform" {
  display_name = "academy-terraform"

  # Cancellarlo toglierebbe al workflow le credenziali con cui gira.
  lifecycle {
    prevent_destroy = true
  }
}

data "databricks_group" "admins" {
  display_name = "admins"
}

resource "databricks_group_member" "terraform_admin" {
  group_id  = data.databricks_group.admins.id
  member_id = databricks_service_principal.terraform.id
}

# Admin del workspace non basta per creare cataloghi (terraform_data.catalogo in
# infra/databricks): serve CREATE CATALOG sul metastore. Grant singolo, non
# autoritativo: gli altri grant del metastore restano com'erano.
data "databricks_current_metastore" "questo" {}

resource "databricks_grant" "terraform_crea_catalogo" {
  metastore  = data.databricks_current_metastore.questo.id
  principal  = databricks_service_principal.terraform.application_id
  privileges = ["CREATE_CATALOG"]
}

# Il secret scade dopo un anno; dopo 11 mesi un plan dal PC propone di sostituirlo.
# Il nuovo nasce prima che il vecchio sia cancellato e va subito negli environment.
resource "time_rotating" "secret_terraform" {
  rotation_days = 335
}

resource "databricks_service_principal_secret" "terraform" {
  service_principal_id = databricks_service_principal.terraform.id
  lifetime             = "31536000s"

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [time_rotating.secret_terraform]
  }
}

data "databricks_current_config" "questo" {}

locals {
  # Nomi letti dal provider databricks e dalla CLI nel workflow.
  credenziali = {
    DATABRICKS_HOST          = data.databricks_current_config.questo.host
    DATABRICKS_CLIENT_ID     = databricks_service_principal.terraform.application_id
    DATABRICKS_CLIENT_SECRET = databricks_service_principal_secret.terraform.secret
  }

  # "infra-plan/DATABRICKS_HOST" => { environment, nome }
  secret_github = merge([
    for env in var.environment_github : {
      for nome in keys(local.credenziali) : "${env}/${nome}" => { environment = env, nome = nome }
    }
  ]...)
}

# Le credenziali passano da un provider all'altro senza che nessuno le veda; stanno
# nello stato di HCP, cifrato. Anche l'host è un secret: il repository è pubblico.
resource "github_actions_environment_secret" "databricks" {
  for_each = local.secret_github

  repository      = var.repository
  environment     = each.value.environment
  secret_name     = each.value.nome
  plaintext_value = local.credenziali[each.value.nome]
}
