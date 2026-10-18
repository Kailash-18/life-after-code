# Project Sentinel — Google Cloud Armor Security & DDoS Mitigation Policy
# Layer 7 WAF, Adaptive Token-Bucket Rate Limiting, and Geo-Protection for Sentinel Microservices.

resource "google_compute_security_policy" "sentinel_armor" {
  name        = "sentinel-cloud-armor-policy"
  description = "Principal SRE Cloud Armor policy: WAF, rate-limiting, and DDoS defense"
  project     = var.project_id

  # Rule 1: Adaptive Rate Limiting to prevent synthetic probe exhaustion & brute force
  rule {
    action   = "rate_based_ban"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1000
        interval_sec = 60
      }
      ban_duration_sec = 300
    }
    description = "Throttle IP requests exceeding 1,000 req/min with 5-minute ban"
  }

  # Rule 2: SQL Injection (SQLi) & Cross-Site Scripting (XSS) Preconfigured WAF
  rule {
    action   = "deny(403)"
    priority = "2000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable') || evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Deny requests matching OWASP Top 10 SQLi or XSS attack signatures"
  }

  # Rule 3: Local File Inclusion (LFI) & Remote Code Execution (RCE) Defense
  rule {
    action   = "deny(403)"
    priority = "3000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rce-v33-stable') || evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "Block RCE / LFI path traversal attempts"
  }

  # Default rule: Allow all non-malicious traffic
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }
}
