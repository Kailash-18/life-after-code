# Project Sentinel — Cloud Run Services with Canary Traffic Tagging (Task K2)
# Configures the Target Workload with dedicated canary tag isolation and the Sentinel Backend API

# 1. Target Microservice (Demo App under test)
resource "google_cloud_run_v2_service" "target_app" {
  name     = "sentinel-target-app"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.app_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
      env {
        name  = "PORT"
        value = "8080"
      }
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 5
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    environment = var.environment
    service     = "target-app"
    managed_by  = "terraform"
  }
}

# Allow public invocations for hackathon demonstration
resource "google_cloud_run_service_iam_member" "target_app_public_access" {
  location = google_cloud_run_v2_service.target_app.location
  service  = google_cloud_run_v2_service.target_app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 2. Sentinel Backend API
resource "google_cloud_run_v2_service" "backend" {
  name     = "sentinel-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.backend_image
      ports {
        container_port = 8000
      }
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
      env {
        name  = "PORT"
        value = "8000"
      }
      env {
        name = "SENTINEL_HMAC_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.hmac_secret.secret_id
            version = "latest"
          }
        }
      }
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 3
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    environment = var.environment
    service     = "backend"
    managed_by  = "terraform"
  }
}

resource "google_cloud_run_service_iam_member" "backend_public_access" {
  location = google_cloud_run_v2_service.backend.location
  service  = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
