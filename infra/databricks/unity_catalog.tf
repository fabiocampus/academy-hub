# Parte analitica (ADR-0011): un catalogo per ambiente con i livelli medallion.

data "databricks_sql_warehouse" "report" {
  name = var.warehouse
}

# Free Edition: il metastore non ha uno storage root, quindi l'API dei cataloghi
# (e databricks_catalog) rifiuta di crearli. In SQL invece nascono sul Default
# Storage. Idempotente: un catalogo che esiste già resta com'è. Un destroy non lo
# cancella: si cancella solo a mano, con i suoi dati.
resource "terraform_data" "catalogo" {
  for_each = var.cataloghi

  triggers_replace = [each.value]

  provisioner "local-exec" {
    command = "python ${path.module}/crea_catalogo.py ${each.value}"
    environment = {
      WAREHOUSE_ID = data.databricks_sql_warehouse.report.id
    }
  }
}

locals {
  livelli = {
    bronze = "Dati grezzi, come arrivano dalle sorgenti"
    silver = "Dati puliti e validati"
    gold   = "Aggregati per i report"
  }

  # "collaudo/gold" => { catalogo, schema, commento }
  schemi = merge([
    for target, catalogo in var.cataloghi : {
      for schema, commento in local.livelli :
      "${target}/${schema}" => { catalogo = catalogo, schema = schema, commento = commento }
    }
  ]...)
}

resource "databricks_schema" "livello" {
  for_each = local.schemi

  catalog_name = terraform_data.catalogo[split("/", each.key)[0]].triggers_replace[0]
  name         = each.value.schema
  comment      = each.value.commento

  # Con le tabelle dentro: né in prod né in collaudo si cancellano da Terraform.
  lifecycle {
    prevent_destroy = true
  }
}

# Grant autoritativi: quello che non è qui, Terraform lo toglie (e il plan del
# lunedì lo segnala come deriva). Il proprietario del catalogo non compare: ha i
# diritti senza grant.
resource "databricks_grants" "catalogo" {
  for_each = var.cataloghi

  catalog = terraform_data.catalogo[each.key].triggers_replace[0]

  # Gli utenti vedono il catalogo; leggono solo gold.
  grant {
    principal  = "account users"
    privileges = ["USE_CATALOG"]
  }

  # Il service principal di Terraform gestisce schemi e grant anche nei cataloghi
  # creati dal PC, di cui non è proprietario.
  grant {
    principal  = data.databricks_service_principal.terraform.application_id
    privileges = ["ALL_PRIVILEGES", "MANAGE"]
  }
}

resource "databricks_grants" "gold" {
  for_each = var.cataloghi

  schema = databricks_schema.livello["${each.key}/gold"].id

  grant {
    principal  = "account users"
    privileges = ["USE_SCHEMA", "SELECT"]
  }
}

# Per i secret dell'App e delle pipeline delle fasi successive. Chi la crea ne ha
# MANAGE; gli altri non la leggono.
resource "databricks_secret_scope" "academy" {
  name = "academy-hub"
}
