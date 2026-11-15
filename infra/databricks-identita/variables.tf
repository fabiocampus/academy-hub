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

variable "environment_github" {
  description = "Environment di GitHub che ricevono le credenziali del service principal (plan e apply)."
  type        = set(string)
  default     = ["infra-plan", "infra"]
}

variable "environment_rilascio" {
  description = "Environment di GitHub del workflow rilascio.yml (creati da infra/github)."
  type        = set(string)
  default     = ["collaudo", "prod"]
}
