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
