locals {
  tables = {
    listings      = { partition = null, clustering = ["source", "brand_norm", "model_norm"] }
    evaluations   = { partition = "evaluated_at", clustering = ["source", "listing_id"] }
    alerts        = { partition = "sent_at", clustering = ["source", "listing_id"] }
    feedback      = { partition = "created_at", clustering = ["source", "listing_id"] }
    geocode_cache = { partition = null, clustering = ["postal_code"] }
    tech_alerts   = { partition = null, clustering = ["kind"] }
  }
  # Ordre de création : chaque vue dépend des précédentes.
  views = ["v_latest_evaluation", "v_latest_feedback", "v_listing_status"]
}

resource "google_bigquery_dataset" "main" {
  dataset_id  = var.dataset_id
  location    = var.bq_location
  description = "Sourcing de véhicules : annonces, évaluations, alertes et retours."
  depends_on  = [google_project_service.apis]
}

resource "google_bigquery_table" "tables" {
  for_each            = local.tables
  dataset_id          = google_bigquery_dataset.main.dataset_id
  table_id            = each.key
  schema              = file("${path.module}/../sql/schemas/${each.key}.json")
  clustering          = each.value.clustering
  deletion_protection = true

  dynamic "time_partitioning" {
    for_each = each.value.partition == null ? [] : [each.value.partition]
    content {
      type  = "DAY"
      field = time_partitioning.value
    }
  }
}

resource "google_bigquery_table" "v_latest_evaluation" {
  dataset_id          = google_bigquery_dataset.main.dataset_id
  table_id            = "v_latest_evaluation"
  deletion_protection = false
  view {
    query          = templatefile("${path.module}/../sql/views/v_latest_evaluation.sql", { project = var.project_id, dataset = var.dataset_id })
    use_legacy_sql = false
  }
  depends_on = [google_bigquery_table.tables]
}

resource "google_bigquery_table" "v_latest_feedback" {
  dataset_id          = google_bigquery_dataset.main.dataset_id
  table_id            = "v_latest_feedback"
  deletion_protection = false
  view {
    query          = templatefile("${path.module}/../sql/views/v_latest_feedback.sql", { project = var.project_id, dataset = var.dataset_id })
    use_legacy_sql = false
  }
  depends_on = [google_bigquery_table.tables]
}

resource "google_bigquery_table" "v_listing_status" {
  dataset_id          = google_bigquery_dataset.main.dataset_id
  table_id            = "v_listing_status"
  deletion_protection = false
  view {
    query          = templatefile("${path.module}/../sql/views/v_listing_status.sql", { project = var.project_id, dataset = var.dataset_id })
    use_legacy_sql = false
  }
  depends_on = [google_bigquery_table.v_latest_evaluation, google_bigquery_table.v_latest_feedback]
}
