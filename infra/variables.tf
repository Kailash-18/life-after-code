# Project Sentinel — Infrastructure Variables & Security Configuration
# Parameterizes all compute sizing, network boundaries, rate limits, and cryptographic secrets.

variable "project_id" {
  description = "Google Cloud Project ID for Project Sentinel"
  type        = string
  default     = "project-sentinel-hackathon"
}

variable "region" {
  description = "Default GCP Region for Primary Cloud Run & Artifact Registry"
  type        = string
  default     = "us-central1"
}

variable "failover_region" {
  description = "Secondary disaster recovery GCP Region for Active-Active Multi-Region Cloud Run"
  type        = string
  default     = "us-east1"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "gitlab_project_path" {
  description = "GitLab project path (namespace/project) for Workload Identity Federation condition checking"
  type        = string
  default     = "project-sentinel/sentinel"
}

variable "app_image" {
  description = "Container image URI for the Sentinel Target App"
  type        = string
  default     = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/target-app:stable"
}

variable "backend_image" {
  description = "Container image URI for the Sentinel Backend API"
  type        = string
  default     = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/backend:latest"
}

# --- Cryptographic & Sensitive Credentials ---

variable "initial_hmac_secret" {
  description = "Cryptographic secret key for HMAC-SHA256 event signature verification"
  type        = string
  sensitive   = true
  default     = "hackathon-transcend-sentinel-key-2026"
}

# --- Cloud Armor Security & Rate Limiting ---

variable "cloud_armor_policy_name" {
  description = "Resource name of the Google Cloud Armor Layer 7 WAF policy"
  type        = string
  default     = "sentinel-cloud-armor-policy"
}

variable "rate_limit_threshold_count" {
  description = "Maximum HTTP request volume permitted per IP within the rate-limit window"
  type        = number
  default     = 1000
}

variable "rate_limit_interval_sec" {
  description = "Rate limiting evaluation window duration in seconds"
  type        = number
  default     = 60
}

variable "rate_limit_ban_duration_sec" {
  description = "Banning duration in seconds for clients violating rate limiting thresholds"
  type        = number
  default     = 300
}

# --- Cloud Run Workload Compute Sizing ---

variable "target_app_cpu" {
  description = "CPU allocation for target app container instance"
  type        = string
  default     = "1000m"
}

variable "target_app_memory" {
  description = "Memory allocation for target app container instance"
  type        = string
  default     = "512Mi"
}

variable "target_app_min_instances" {
  description = "Minimum standby instances for target app (cold start prevention)"
  type        = number
  default     = 1
}

variable "target_app_max_instances" {
  description = "Maximum scaling instances for target app"
  type        = number
  default     = 5
}

variable "backend_cpu" {
  description = "CPU allocation for Sentinel backend container instance"
  type        = string
  default     = "1000m"
}

variable "backend_memory" {
  description = "Memory allocation for Sentinel backend container instance"
  type        = string
  default     = "512Mi"
}

variable "backend_min_instances" {
  description = "Minimum standby instances for Sentinel backend"
  type        = number
  default     = 1
}

variable "backend_max_instances" {
  description = "Maximum scaling instances for Sentinel backend"
  type        = number
  default     = 3
}

# --- Networking, Load Balancer & DNS ---

variable "backend_timeout_sec" {
  description = "HTTP backend service response timeout in seconds"
  type        = number
  default     = 30
}

variable "lb_forwarding_port" {
  description = "Global forwarding rule ingress port"
  type        = string
  default     = "80"
}

variable "dns_domain_name" {
  description = "Internal domain name for Cloud DNS anycast multi-region mesh"
  type        = string
  default     = "sentinel-mesh.internal."
}

variable "dns_ttl" {
  description = "DNS Time-To-Live in seconds for fast anycast failover propagation"
  type        = number
  default     = 5
}
