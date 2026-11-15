# Parte analitica della fase 11 (ADR-0016): il database di Lakebase registrato in
# Unity Catalog e i grant per il service principal che fa il deploy del bundle
# (academy-rilascio), con cui girano il job `analisi` e la pipeline `storico`.

data "databricks_service_principal" "rilascio" {
  display_name = "academy-rilascio"
}

# Un catalogo per ambiente, `<catalogo>_oltp`, sul branch Lakebase dell'ambiente.
# Contiene tutti gli schemi del database (anche quello dell'altro ambiente, se il
# branch è una copia): il job legge solo lo schema del suo target. Lettura in sola
# lettura dal compute serverless, nessun ruolo Postgres per chi legge.
resource "databricks_postgres_catalog" "oltp" {
  for_each = var.cataloghi

  catalog_id = "${each.value}_oltp"
  spec = {
    postgres_database = var.database_lakebase
    branch            = "projects/${var.progetto_lakebase}/branches/${var.rami_lakebase[each.key]}"
  }
}

resource "databricks_grants" "oltp" {
  for_each = var.cataloghi

  catalog = databricks_postgres_catalog.oltp[each.key].catalog_id

  # Lo snapshot giornaliero legge le tabelle dell'App.
  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT"]
  }

  grant {
    principal  = data.databricks_service_principal.terraform.application_id
    privileges = ["ALL_PRIVILEGES", "MANAGE"]
  }
}

# Il job scrive gli snapshot in bronze, la pipeline lo storico in silver. Le tabelle
# che creano sono loro: per leggerle e riscriverle bastano i diritti del proprietario.
resource "databricks_grants" "bronze" {
  for_each = var.cataloghi

  schema = databricks_schema.livello["${each.key}/bronze"].id

  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_SCHEMA", "CREATE_TABLE"]
  }
}

resource "databricks_grants" "silver" {
  for_each = var.cataloghi

  schema = databricks_schema.livello["${each.key}/silver"].id

  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW"]
  }
}
