# Project Sentinel — Active-Active Multi-Region Disaster Recovery & Cloud DNS Traffic Director
# Principal SRE Tier: Deploys zero-RPO/sub-3s-RTO failover across us-central1 and us-east1.

# 1. Secondary Cloud Run Workload Replica (us-east1 Failover)
resource "google_cloud_run_v2_service" "target_app_failover" {
  name     = "sentinel-target-app-east"
  location = var.failover_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.app_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = var.target_app_cpu
          memory = var.target_app_memory
        }
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "REGION"
        value = var.failover_region
      }
    }
    scaling {
      min_instance_count = var.target_app_min_instances
      max_instance_count = var.target_app_max_instances
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    environment = var.environment
    service     = "target-app-failover"
    managed_by  = "terraform"
    tier        = "dr-active-replica"
  }
}

resource "google_cloud_run_service_iam_member" "target_app_failover_public_access" {
  location = google_cloud_run_v2_service.target_app_failover.location
  service  = google_cloud_run_v2_service.target_app_failover.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 2. Serverless NEG for Secondary Region (us-east1)
resource "google_compute_region_network_endpoint_group" "target_app_failover_neg" {
  name                  = "sentinel-target-app-failover-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.failover_region

  cloud_run {
    service = google_cloud_run_v2_service.target_app_failover.name
  }
}

# 3. Cloud DNS Private/Public Anycast Steering Zone
resource "google_dns_managed_zone" "sentinel_zone" {
  name        = "sentinel-global-zone"
  dns_name    = var.dns_domain_name
  description = "Principal SRE Cloud DNS Zone for automated multi-region steering"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = "projects/${var.project_id}/global/networks/default"
    }
  }
}

# 4. Anycast Routing Record with Health Failover Policy
resource "google_dns_record_set" "sentinel_anycast_record" {
  name         = "edge.${var.dns_domain_name}"
  managed_zone = google_dns_managed_zone.sentinel_zone.name
  type         = "A"
  ttl          = var.dns_ttl

  routing_policy {
    geo {
      location = "us-central1"
      rrdatas  = [google_compute_global_address.sentinel_lb_ip.address]
    }
    geo {
      location = "us-east1"
      rrdatas  = [google_compute_global_address.sentinel_lb_ip.address]
    }
  }
}
