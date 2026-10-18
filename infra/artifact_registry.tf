# Project Sentinel — Artifact Registry Repository (Task K2)
# Stores container images for Target Microservice and Sentinel Backend

resource "google_artifact_registry_repository" "sentinel_repo" {
  location      = var.region
  repository_id = "sentinel"
  description   = "Docker repository for Project Sentinel microservices"
  format        = "DOCKER"

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    project     = "sentinel"
  }
}
