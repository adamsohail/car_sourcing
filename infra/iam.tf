# Compte de service d'exécution (job et service). Son email est à partager en lecture sur le Google Sheet.
resource "google_service_account" "runtime" {
  account_id   = "car-sourcing-run"
  display_name = "Sourcing auto : exécution"
  depends_on   = [google_project_service.apis]
}

resource "google_bigquery_dataset_iam_member" "runtime_editor" {
  dataset_id = google_bigquery_dataset.main.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Cloud Scheduler déclenche le job avec ce compte.
resource "google_service_account" "scheduler" {
  account_id   = "car-sourcing-scheduler"
  display_name = "Sourcing auto : planification"
  depends_on   = [google_project_service.apis]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  name     = google_cloud_run_v2_job.ingest.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# Déploiement depuis GitHub Actions sans clé (Workload Identity Federation).
resource "google_service_account" "deployer" {
  account_id   = "car-sourcing-deploy"
  display_name = "Sourcing auto : déploiement GitHub"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = toset(["roles/run.developer", "roles/artifactregistry.writer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = var.github_repository == "" ? 0 : 1
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.github_repository == "" ? 0 : 1
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonation" {
  count              = var.github_repository == "" ? 0 : 1
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}
