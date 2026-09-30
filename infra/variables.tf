variable "project_id" {
  type        = string
  description = "Identifiant du projet GCP."
}

variable "region" {
  type        = string
  default     = "europe-west1"
  description = "Région Cloud Run, Artifact Registry et Cloud Scheduler."
}

variable "bq_location" {
  type    = string
  default = "EU"
}

variable "dataset_id" {
  type    = string
  default = "car_sourcing"
}

variable "sheet_id" {
  type        = string
  default     = ""
  description = "Identifiant du Google Sheet de configuration (dans son URL, entre /d/ et /edit)."
}

variable "telegram_chat_id" {
  type        = string
  default     = ""
  description = "Identifiant du groupe Telegram qui reçoit les alertes (commence souvent par -100)."
}

variable "github_repository" {
  type        = string
  default     = ""
  description = "Dépôt GitHub au format proprietaire/nom, autorisé à déployer via Workload Identity Federation."
}

variable "image" {
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
  description = "Image initiale ; la CI la remplace à chaque déploiement (Terraform ignore ensuite ce champ)."
}

variable "schedule" {
  type    = string
  default = "*/10 * * * *"
}
