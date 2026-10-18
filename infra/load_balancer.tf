# Project Sentinel — Global HTTPS Load Balancer with Multi-Region Serverless NEGs
# Connects Google Cloud Armor Layer 7 WAF, Cloud Run Serverless NEGs, and Anycast CDN.

# 1. Serverless Network Endpoint Groups (NEGs) for Cloud Run Services
resource "google_compute_region_network_endpoint_group" "target_app_neg" {
  name                  = "sentinel-target-app-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = google_cloud_run_v2_service.target_app.name
  }
}

resource "google_compute_region_network_endpoint_group" "backend_neg" {
  name                  = "sentinel-backend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = google_cloud_run_v2_service.backend.name
  }
}

# 2. Backend Service for Target Application with Cloud Armor Attachment
resource "google_compute_backend_service" "target_app_backend" {
  name                  = "sentinel-target-app-backend"
  description           = "Production backend service for canary/stable target workload"
  protocol              = "HTTPS"
  port_name             = "http"
  timeout_sec           = var.backend_timeout_sec
  enable_cdn            = false
  security_policy       = google_compute_security_policy.sentinel_armor.id
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.target_app_neg.id
  }

  backend {
    group = google_compute_region_network_endpoint_group.target_app_failover_neg.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}


# 3. Backend Service for Sentinel API with Cloud Armor Attachment
resource "google_compute_backend_service" "sentinel_api_backend" {
  name                  = "sentinel-api-backend"
  description           = "Production backend service for Sentinel Mission Control FastAPI"
  protocol              = "HTTPS"
  port_name             = "http"
  timeout_sec           = var.backend_timeout_sec
  enable_cdn            = false
  security_policy       = google_compute_security_policy.sentinel_armor.id
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.backend_neg.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# 4. Global URL Map Routing (Host/Path based routing to Target Workload vs Sentinel API)
resource "google_compute_url_map" "sentinel_url_map" {
  name            = "sentinel-global-url-map"
  description     = "Global L7 Anycast routing table for Project Sentinel"
  default_service = google_compute_backend_service.target_app_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "allpaths"
  }

  path_matcher {
    name            = "allpaths"
    default_service = google_compute_backend_service.target_app_backend.id

    path_rule {
      paths   = ["/api/*", "/docs", "/openapi.json"]
      service = google_compute_backend_service.sentinel_api_backend.id
    }
  }
}

# 5. Global Anycast Reserved IPv4 Address
resource "google_compute_global_address" "sentinel_lb_ip" {
  name        = "sentinel-lb-ipv4"
  description = "Anycast static IPv4 address for Project Sentinel Global Edge"
}

# 6. Global Target HTTP Proxy
resource "google_compute_target_http_proxy" "sentinel_http_proxy" {
  name    = "sentinel-http-proxy"
  url_map = google_compute_url_map.sentinel_url_map.id
}

# 7. Global Forwarding Rule (Port 80 Ingress)
resource "google_compute_global_forwarding_rule" "sentinel_forwarding_rule" {
  name                  = "sentinel-global-forwarding-rule"
  description           = "Global L7 Ingress Forwarding Rule"
  ip_protocol           = "TCP"
  port_range            = var.lb_forwarding_port
  target                = google_compute_target_http_proxy.sentinel_http_proxy.id
  ip_address            = google_compute_global_address.sentinel_lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
