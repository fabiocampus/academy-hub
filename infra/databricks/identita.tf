# Il service principal del workflow lo gestisce infra/databricks-identita (solo dal
# PC, ADR-0012); qui serve il suo application id per i grant.
data "databricks_service_principal" "terraform" {
  display_name = "academy-terraform"
}
