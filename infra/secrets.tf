# Project Sentinel — Secret Manager Configuration (Task K2)
# Secure storage for CI HMAC secrets and GitLab tokens without committing secrets to repository

resource "google_secret_manager_secret" "hmac_secret" {
  secret_id = "sentinel-hmac-secret"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "google_secret_manager_secret_version" "hmac_secret_initial" {
  secret      = google_secret_manager_secret.hmac_secret.id
  secret_data = var.initial_hmac_secret
}


# Grant backend service account permission to access the secret
resource "google_secret_manager_secret_iam_member" "backend_hmac_access" {
  secret_id = google_secret_manager_secret.hmac_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ci_runner_sa.email}"
}
