# Importazioni di presenze e valutazioni e controlli di qualità (ADR-0017). I CSV si
# caricano nel volume `bronze.importazioni`, una cartella per tipo; la pipeline `storico`
# li legge con Auto Loader e scrive righe scartate e stato dei file nello schema
# `qualita`, dove il job `analisi` fissa i verdetti e registra gli esiti.

resource "databricks_volume" "importazioni" {
  for_each = var.cataloghi

  catalog_name = databricks_schema.livello["${each.key}/bronze"].catalog_name
  schema_name  = databricks_schema.livello["${each.key}/bronze"].name
  name         = "importazioni"
  volume_type  = "MANAGED"
  comment      = "CSV di presenze e valutazioni da importare (solo dati sintetici)"

  # Cancellarlo cancellerebbe i file caricati, che lo stato dei file e i verdetti citano.
  lifecycle {
    prevent_destroy = true
  }
}

locals {
  # "collaudo/presenze" => { target, tipo }
  cartelle_importazioni = merge([
    for target in keys(var.cataloghi) : {
      for tipo in ["presenze", "valutazioni"] :
      "${target}/${tipo}" => { target = target, tipo = tipo }
    }
  ]...)
}

# Un volume non ha cartelle vuote: un file le crea, così Auto Loader trova la cartella
# alla prima passata. Legge solo `*.csv`, quindi questo file resta fuori.
resource "databricks_file" "leggimi" {
  for_each = local.cartelle_importazioni

  path = "${databricks_volume.importazioni[each.value.target].volume_path}/${each.value.tipo}/LEGGIMI.txt"
  content_base64 = base64encode(<<-EOT
    Carica qui i CSV di ${each.value.tipo} (UTF-8, con intestazione, estensione .csv).
    Colonne: ${each.value.tipo == "presenze" ? "edizione_id,email,giorno (AAAA-MM-GG)" : "edizione_id,email,voto (1-5),commento"}.
    Un file già caricato non viene riletto: un file corretto va caricato con un nome nuovo.
    Solo dati sintetici. Esempi in data/samples/ del repository.
  EOT
  )
}

resource "databricks_grants" "importazioni" {
  for_each = var.cataloghi

  volume = databricks_volume.importazioni[each.key].id

  # La pipeline legge i file con l'identità del service principal del rilascio.
  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["READ_VOLUME"]
  }

  dynamic "grant" {
    for_each = contains(var.importazioni_aperte, each.key) ? [1] : []
    content {
      principal  = "account users"
      privileges = ["READ_VOLUME", "WRITE_VOLUME"]
    }
  }
}

# Pipeline (quarantene, file_importati) e task del job (verdetti, esiti) creano le loro
# tabelle e viste materializzate; per rileggerle bastano i diritti del proprietario.
resource "databricks_grants" "qualita" {
  for_each = var.cataloghi

  schema = databricks_schema.livello["${each.key}/qualita"].id

  grant {
    principal  = data.databricks_service_principal.rilascio.application_id
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW"]
  }
}
