output "service_url" {
  value       = local.service_url
  description = "Adresse de l'interface et du webhook Telegram."
}

output "runtime_service_account" {
  value       = google_service_account.runtime.email
  description = "À partager en lecture seule sur le Google Sheet de configuration."
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}

output "workload_identity_provider" {
  value = var.github_repository == "" ? "" : google_iam_workload_identity_pool_provider.github[0].name
}
