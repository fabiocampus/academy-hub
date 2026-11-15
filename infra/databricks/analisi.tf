# Parte analitica della fase 11 (ADR-0016): il database di Lakebase registrato in
# Unity Catalog e i grant per il service principal che fa il deploy del bundle
# (academy-rilascio), con cui girano il job `analisi` e la pipeline `storico`.

data "databricks_service_principal" "rilascio" {
  display_name = "academy-rilascio"
}

# Un catalogo per ambiente, `<catalogo>_oltp`, sul branch Lakebase dell'ambiente.
# Contiene tutti gli schemi del database (anche quello dell'altro ambiente, se il
# branch è una copia): per questo i grant di lettura sono sullo schema del target,
# non sul catalogo. Lettura in sola lettura dal compute serverless.
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

  # Solo l'accesso al catalogo: cosa si legge lo dicono i grant sullo schema.
  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_CATALOG"]
  }

  grant {
    principal  = data.databricks_service_principal.terraform.application_id
    privileges = ["ALL_PRIVILEGES", "MANAGE"]
  }
}

# Gli schemi di un catalogo Lakebase appena registrato non esistono per l'API di Unity
# Catalog finché una query non li legge: senza questo passo il grant sullo schema
# fallisce con "does not exist". Si ripete solo se il catalogo viene ricreato.
resource "terraform_data" "schemi_oltp" {
  for_each = var.cataloghi

  triggers_replace = [databricks_postgres_catalog.oltp[each.key].uid]

  provisioner "local-exec" {
    command = "python ${path.module}/carica_schemi.py ${databricks_postgres_catalog.oltp[each.key].catalog_id}"
    environment = {
      WAREHOUSE_ID = data.databricks_sql_warehouse.report.id
    }
  }
}

# Lo snapshot giornaliero legge le tabelle dell'App, solo dallo schema del suo target.
resource "databricks_grants" "oltp_schema" {
  for_each = var.cataloghi

  depends_on = [terraform_data.schemi_oltp]

  schema = "${databricks_postgres_catalog.oltp[each.key].catalog_id}.${var.schemi_lakebase[each.key]}"

  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_SCHEMA", "SELECT"]
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

  # Per arrivare al volume delle importazioni (qualita.tf), dove in collaudo tutti
  # possono caricare file. Solo l'accesso allo schema: le tabelle non le leggono.
  dynamic "grant" {
    for_each = contains(var.importazioni_aperte, each.key) ? [1] : []
    content {
      principal  = "account users"
      privileges = ["USE_SCHEMA"]
    }
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
