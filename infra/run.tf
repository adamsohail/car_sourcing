locals {
  service_name = "car-sourcing-web"
  job_name     = "car-sourcing-ingest"
  # URL déterministe de Cloud Run : sert aux liens « Ouvrir la fiche » des alertes Telegram.
  service_url = "https://${local.service_name}-${data.google_project.this.number}.${var.region}.run.app"
  common_env = {
    GCP_PROJECT      = var.project_id
    BQ_DATASET       = var.dataset_id
    BQ_LOCATION      = var.bq_location
    SHEET_ID         = var.sheet_id
    TELEGRAM_CHAT_ID = var.telegram_chat_id
    PUBLIC_BASE_URL  = local.service_url
  }
  secret_env = {
    GMAIL_OAUTH_JSON        = "gmail-oauth-json"
    TELEGRAM_BOT_TOKEN      = "telegram-bot-token"
    TELEGRAM_WEBHOOK_SECRET = "telegram-webhook-secret"
    WEB_PASSWORD            = "web-password"
    SESSION_SECRET          = "session-secret"
  }
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "car-sourcing"
  location      = var.region
  format        = "DOCKER"
  cleanup_policies {
    id     = "garder-les-10-dernieres"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_job" "ingest" {
  name                = local.job_name
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.runtime.email
      timeout         = "540s"
      max_retries     = 0
      containers {
        image = var.image
        args  = ["run"]
        resources {
          limits = { cpu = "1", memory = "512Mi" }
        }
        dynamic "env" {
          for_each = local.common_env
          content {
            name  = env.key
            value = env.value
          }
        }
        dynamic "env" {
          for_each = local.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.secrets[env.value].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime_access, google_secret_manager_secret_version.placeholder]
}

resource "google_cloud_scheduler_job" "ingest" {
  name             = "car-sourcing-toutes-les-10-minutes"
  region           = var.region
  schedule         = var.schedule
  time_zone        = "Europe/Paris"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.ingest.name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_invoker]
}

resource "google_cloud_run_v2_service" "web" {
  name                = local.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.image
      args  = ["serve"]
      ports {
        container_port = 8080
      }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.secrets[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
      startup_probe {
        http_get {
          path = "/healthz"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime_access, google_secret_manager_secret_version.placeholder]
}

# Accès public : Telegram doit joindre le webhook ; l'interface et l'API demandent un mot de passe.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
