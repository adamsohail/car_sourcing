terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Bucket créé par scripts/bootstrap.sh ; passé à `terraform init -backend-config="bucket=..."`.
  backend "gcs" {
    prefix = "car-sourcing/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
