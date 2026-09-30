# Les secrets saisis à la main reçoivent une valeur provisoire, remplacée ensuite avec
# `scripts/set_secret.sh` : la dernière version est lue à chaque exécution.
locals {
  manual_secrets    = ["gmail-oauth-json", "telegram-bot-token", "web-password"]
  generated_secrets = ["telegram-webhook-secret", "session-secret"]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(concat(local.manual_secrets, local.generated_secrets))
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "placeholder" {
  for_each    = toset(local.manual_secrets)
  secret      = google_secret_manager_secret.secrets[each.value].id
  secret_data = "A_REMPLACER"
  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "random_password" "generated" {
  for_each = toset(local.generated_secrets)
  length   = 48
  special  = false
}

resource "google_secret_manager_secret_version" "generated" {
  for_each    = toset(local.generated_secrets)
  secret      = google_secret_manager_secret.secrets[each.value].id
  secret_data = random_password.generated[each.value].result
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each  = google_secret_manager_secret.secrets
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
