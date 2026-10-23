# ==============================================================================
# Project Sentinel — Local / CI Environment Configuration
# ==============================================================================

project_id          = "project-sentinel-hackathon"
region              = "us-central1"
failover_region     = "us-east1"
environment         = "prod"
gitlab_project_path = "project-sentinel/sentinel"

app_image     = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/target-app:stable"
backend_image = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/backend:latest"

# 3. Cryptographic Secret Keys (Do NOT commit production keys to git; pass via TF_VAR_initial_hmac_secret)
initial_hmac_secret = "dev-insecure-hmac-secret-min16chars"

cloud_armor_policy_name     = "sentinel-cloud-armor-policy"
rate_limit_threshold_count  = 1000
rate_limit_interval_sec     = 60
rate_limit_ban_duration_sec = 300

target_app_cpu           = "1000m"
target_app_memory        = "512Mi"
target_app_min_instances = 1
target_app_max_instances = 5

backend_cpu           = "1000m"
backend_memory        = "512Mi"
backend_min_instances = 1
backend_max_instances = 3

backend_timeout_sec = 30
lb_forwarding_port  = "80"
dns_domain_name     = "sentinel-mesh.internal."
dns_ttl             = 5

# 7. Cross-Region Disaster Recovery & Migration via S3
migration_snapshot_s3_bucket = "sentinel-region-migration-snapshots"
migration_target_region      = "us-east1"

# 8. Zero-Trust Cloud Run Perimeter Controls
cloud_run_ingress                 = "INGRESS_TRAFFIC_ALL"
allow_unauthenticated_invocations = true

# 9. AWS S3 Remote State & DynamoDB Distributed Locking
aws_state_region          = "us-east-1"
state_bucket_name         = "sentinel-terraform-state-prod"
dynamodb_lock_table_name  = "sentinel-terraform-state-locks"
enable_s3_state_bootstrap = true

