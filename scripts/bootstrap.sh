#!/usr/bin/env bash
# Premier déploiement de l'infrastructure. Usage : scripts/bootstrap.sh <project_id> [region]
# Prérequis : gcloud et terraform installés, `gcloud auth login` et `gcloud auth application-default login` faits
# avec un compte Owner du projet, et infra/terraform.tfvars rempli (voir terraform.tfvars.example).
set -euo pipefail
PROJECT="${1:?project_id manquant}"
REGION="${2:-europe-west1}"
BUCKET="${PROJECT}-tfstate"

gcloud config set project "$PROJECT"
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com storage.googleapis.com
if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access
  gcloud storage buckets update "gs://${BUCKET}" --versioning
fi

cd "$(dirname "$0")/../infra"
terraform init -backend-config="bucket=${BUCKET}"
terraform apply
echo
echo "Infrastructure prête. Valeurs utiles :"
terraform output
