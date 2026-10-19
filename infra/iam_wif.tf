# Project Sentinel — Keyless CI Authentication via Workload Identity Federation (Task K1)
# Establishes OIDC trust between GitLab CI/CD and Google Cloud without static service account keys

resource "google_iam_workload_identity_pool" "gitlab_pool" {
  provider                  = google-beta
  workload_identity_pool_id = "sentinel-gitlab-pool"
  display_name              = "GitLab CI Pool"
  description               = "Workload Identity Pool for Project Sentinel GitLab CI jobs"
}

resource "google_iam_workload_identity_pool_provider" "gitlab_provider" {
  provider                           = google-beta
  workload_identity_pool_id          = google_iam_workload_identity_pool.gitlab_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-jwt-provider"
  display_name                       = "GitLab OIDC Provider"
  description                        = "OIDC identity provider mapping GitLab ID tokens"

  attribute_mapping = {
    "google.subject"              = "assertion.sub"
    "attribute.aud"               = "assertion.aud"
    "attribute.project_path"      = "assertion.project_path"
    "attribute.project_id"        = "assertion.project_id"
    "attribute.ref"               = "assertion.ref"
    "attribute.ref_type"          = "assertion.ref_type"
    "attribute.ci_config_ref_uri" = "assertion.ci_config_ref_uri"
  }

  oidc {
    issuer_uri = "https://gitlab.com"
    allowed_audiences = [
      "https://gitlab.com"
    ]
  }

  attribute_condition = "assertion.project_path == '${var.gitlab_project_path}'"
}

# CI Service Account for running deployment and verification jobs
resource "google_service_account" "ci_runner_sa" {
  account_id   = "sentinel-ci-runner"
  display_name = "Sentinel CI/CD Deployment Runner"
  description  = "Service Account assumed by GitLab CI via WIF for Cloud Run canary deployments"
}

# Allow GitLab CI WIF principals to impersonate the CI runner service account
resource "google_service_account_iam_member" "wif_sa_impersonation" {
  service_account_id = google_service_account.ci_runner_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab_pool.name}/attribute.project_path/${var.gitlab_project_path}"
}

# Grant necessary Cloud Run and Artifact Registry permissions to CI Runner
resource "google_project_iam_member" "ci_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.ci_runner_sa.email}"
}

resource "google_project_iam_member" "ci_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.ci_runner_sa.email}"
}

resource "google_project_iam_member" "ci_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.ci_runner_sa.email}"
}
