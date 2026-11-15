variable "cataloghi" {
  description = "Un catalogo Unity Catalog per target del bundle (ADR-0011)."
  type        = map(string)
  default = {
    collaudo = "academy_collaudo"
    prod     = "academy_prod"
  }

  validation {
    # Il nome finisce in un'istruzione SQL: solo minuscole, cifre e trattino basso.
    condition     = alltrue([for n in values(var.cataloghi) : can(regex("^[a-z][a-z0-9_]*$", n))])
    error_message = "Nomi di catalogo: minuscole, cifre e trattino basso."
  }
}

variable "warehouse" {
  description = "SQL warehouse con cui si crea il catalogo, cercato per nome (l'id è del workspace)."
  type        = string
  default     = "Serverless Starter Warehouse"
}

variable "progetto_lakebase" {
  description = "Progetto Lakebase dell'App (fase 8), creato dal bundle."
  type        = string
  default     = "academy-hub"
}

variable "database_lakebase" {
  description = "Database Postgres di Lakebase con gli schemi dell'App."
  type        = string
  default     = "databricks_postgres"
}

variable "schemi_lakebase" {
  description = "Schema dell'App nel database di ogni target (var.schema_database del bundle)."
  type        = map(string)
  default = {
    collaudo = "academy_collaudo"
    prod     = "academy"
  }
}

variable "rami_lakebase" {
  description = "Branch Lakebase di ogni target: lo stesso insieme di chiavi di var.cataloghi."
  type        = map(string)
  default = {
    collaudo = "collaudo"
    prod     = "production"
  }
}

variable "importazioni_aperte" {
  description = <<-EOT
    Target in cui tutti gli utenti del workspace possono caricare CSV nel volume delle
    importazioni (ADR-0017). Negli altri carica solo il proprietario del catalogo.
  EOT
  type        = set(string)
  default     = ["collaudo"]
}
