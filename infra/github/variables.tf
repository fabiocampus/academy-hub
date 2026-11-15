variable "proprietario" {
  description = "Utente GitHub proprietario del repository."
  type        = string
  default     = "fabiocampus"
}

variable "repository" {
  description = "Nome del repository."
  type        = string
  default     = "academy-hub"
}

variable "approvatori_infra" {
  description = "Utenti GitHub che approvano l'apply nell'environment infra."
  type        = list(string)
  default     = ["fabiocampus"]
}

variable "approvatori_prod" {
  description = "Utenti GitHub che approvano il rilascio nell'environment prod."
  type        = list(string)
  default     = ["fabiocampus"]
}
