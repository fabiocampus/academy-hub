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
