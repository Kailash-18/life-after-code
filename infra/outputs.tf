output "workload_identity_pool_provider" {
  description = "Full resource name of the Workload Identity Provider for GitLab CI config"
  value       = google_iam_workload_identity_pool_provider.gitlab_provider.name
}

output "ci_service_account_email" {
  description = "Email of the CI runner service account"
  value       = google_service_account.ci_runner_sa.email
}

output "artifact_registry_repo" {
  description = "Docker repository URI in Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.sentinel_repo.repository_id}"
}

output "target_app_url" {
  description = "Public URL of the Target App service"
  value       = google_cloud_run_v2_service.target_app.uri
}

output "backend_url" {
  description = "Public URL of the Sentinel Backend API"
  value       = google_cloud_run_v2_service.backend.uri
}

output "global_lb_ip" {
  description = "Global Anycast Load Balancer IP address"
  value       = google_compute_global_address.sentinel_lb_ip.address
}

output "cloud_armor_policy_id" {
  description = "Cloud Armor WAF Security Policy ID"
  value       = google_compute_security_policy.sentinel_armor.id
}

output "target_app_failover_url" {
  description = "Public URL of the Disaster Recovery Target App service in secondary region"
  value       = google_cloud_run_v2_service.target_app_failover.uri
}

output "cloud_dns_managed_zone" {
  description = "Cloud DNS Anycast Managed Zone for multi-region steering"
  value       = google_dns_managed_zone.sentinel_zone.name
}

output "migration_snapshot_s3_bucket" {
  description = "Configured AWS S3 / S3-compatible bucket for cross-region disaster recovery snapshot archives"
  value       = var.migration_snapshot_s3_bucket
}

output "migration_target_region" {
  description = "Target destination cloud region for disaster recovery migration and automated restoration"
  value       = var.migration_target_region
}

output "cloud_run_ingress" {
  description = "Ingress traffic configuration policy applied to Cloud Run services"
  value       = var.cloud_run_ingress
}

output "terraform_state_s3_bucket" {
  description = "AWS S3 bucket hosting authoritative Terraform remote state and incident snapshots"
  value       = var.enable_s3_state_bootstrap ? aws_s3_bucket.terraform_state[0].id : var.state_bucket_name
}

output "terraform_state_dynamodb_table" {
  description = "AWS DynamoDB table enforcing distributed Terraform state locks"
  value       = var.enable_s3_state_bootstrap ? aws_dynamodb_table.terraform_state_locks[0].id : var.dynamodb_lock_table_name
}

output "terraform_state_kms_key_arn" {
  description = "KMS Customer Managed Key ARN securing S3 state storage and DynamoDB locks"
  value       = var.enable_s3_state_bootstrap ? aws_kms_key.state_key[0].arn : null
}

output "terraform_state_kms_key_alias" {
  description = "KMS Customer Managed Key Alias name"
  value       = var.enable_s3_state_bootstrap ? aws_kms_alias.state_key_alias[0].name : null
}

output "ci_state_access_iam_policy_arn" {
  description = "Scoped IAM Policy ARN for GitLab CI / Terraform runner least privilege state access"
  value       = var.enable_s3_state_bootstrap ? aws_iam_policy.ci_state_access[0].arn : null
}



