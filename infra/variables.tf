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
  description = "Cryptographic secret key for HMAC-SHA256 event signature verification. In production, provide via TF_VAR_initial_hmac_secret or GitLab CI/CD Masked Variables."
  type        = string
  sensitive   = true
  default     = "dev-insecure-hmac-secret-min16chars"

  validation {
    condition     = length(var.initial_hmac_secret) >= 16
    error_message = "The initial_hmac_secret must be at least 16 characters for cryptographic HMAC-SHA256 security."
  }
}

# --- Cross-Region Disaster Recovery & Migration via S3 ---

variable "migration_snapshot_s3_bucket" {
  description = "AWS S3 or S3-compatible bucket name for storing regional disaster recovery snapshot archives"
  type        = string
  default     = "sentinel-region-migration-snapshots"
}

variable "migration_target_region" {
  description = "Target destination cloud region for disaster recovery migration and automated restoration"
  type        = string
  default     = "us-east1"
}

variable "s3_endpoint_url" {
  description = "Custom S3 endpoint URL (supports AWS S3, LocalStack, MinIO, or GCS S3-interoperability)"
  type        = string
  default     = ""
}

# --- Cloud Run Zero-Trust Network & Security Controls ---

variable "cloud_run_ingress" {
  description = "Network ingress restriction for Cloud Run services (INGRESS_TRAFFIC_ALL or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER for zero-trust perimeter)"
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"

  validation {
    condition     = contains(["INGRESS_TRAFFIC_ALL", "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER", "INGRESS_TRAFFIC_INTERNAL_ONLY"], var.cloud_run_ingress)
    error_message = "cloud_run_ingress must be INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER, or INGRESS_TRAFFIC_INTERNAL_ONLY."
  }
}

variable "allow_unauthenticated_invocations" {
  description = "Whether to allow allUsers public invoker access directly to Cloud Run services (set to false to enforce load balancer + WAF ingress only)"
  type        = bool
  default     = true
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

# --- AWS S3 Remote State & DynamoDB Distributed Locking Architecture ---

variable "aws_state_region" {
  description = "AWS region for Terraform S3 state bucket, KMS key, and DynamoDB lock table"
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally unique AWS S3 bucket name for storing enterprise Terraform remote state and incident snapshots"
  type        = string
  default     = "sentinel-terraform-state-prod"
}

variable "dynamodb_lock_table_name" {
  description = "AWS DynamoDB table name for distributed Terraform state locking and concurrency control"
  type        = string
  default     = "sentinel-terraform-state-locks"
}

variable "enable_s3_state_bootstrap" {
  description = "Whether to provision the AWS S3 state bucket, KMS key, and DynamoDB locking table resources in this module"
  type        = bool
  default     = true
}

variable "state_kms_key_deletion_window_in_days" {
  description = "Duration in days after which the KMS CMK key is deleted upon destruction"
  type        = number
  default     = 30
}

