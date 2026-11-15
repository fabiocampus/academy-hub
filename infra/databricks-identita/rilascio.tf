# Identità del workflow rilascio.yml su Databricks (OAuth M2M, ADR-0013): fa il deploy
# del bundle in collaudo e in prod. Free Edition non ha la federation OIDC fra GitHub
# Actions e Databricks, quindi un secret da ruotare, come per academy-terraform.
#
# Uno solo per i due ambienti: il progetto Lakebase è uno, e il branch di collaudo vive
# nel progetto di prod; un service principal di collaudo avrebbe comunque i permessi
# sul progetto di prod. Admin del workspace perché App e progetti Lakebase danno
# CAN_MANAGE al gruppo admins e il bundle crea i permessi delle risorse delle App.

resource "databricks_service_principal" "rilascio" {
  display_name = "academy-rilascio"

  # Lo stato del bundle e il codice delle App stanno nella sua cartella.
  lifecycle {
    prevent_destroy = true
  }
}

resource "databricks_group_member" "rilascio_admin" {
  group_id  = data.databricks_group.admins.id
  member_id = databricks_service_principal.rilascio.id
}

resource "time_rotating" "secret_rilascio" {
  rotation_days = 335
}

resource "databricks_service_principal_secret" "rilascio" {
  service_principal_id = databricks_service_principal.rilascio.id
  lifetime             = "31536000s"

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [time_rotating.secret_rilascio]
  }
}

# Chi applica da PC è la persona admin_academy dell'App: la sua email non sta nel
# repository, che è pubblico, ma solo nei secret degli environment.
data "databricks_current_user" "io" {}

locals {
  valori_rilascio = {
    DATABRICKS_HOST          = data.databricks_current_config.questo.host
    DATABRICKS_CLIENT_ID     = databricks_service_principal.rilascio.application_id
    DATABRICKS_CLIENT_SECRET = databricks_service_principal_secret.rilascio.secret
    ACADEMY_ADMIN_EMAIL      = data.databricks_current_user.io.user_name
  }

  # "collaudo/DATABRICKS_HOST" => { environment, nome }
  secret_rilascio = merge([
    for env in var.environment_rilascio : {
      for nome in keys(local.valori_rilascio) : "${env}/${nome}" => { environment = env, nome = nome }
    }
  ]...)
}

resource "github_actions_environment_secret" "rilascio" {
  for_each = local.secret_rilascio

  repository      = var.repository
  environment     = each.value.environment
  secret_name     = each.value.nome
  plaintext_value = local.valori_rilascio[each.value.nome]
}
