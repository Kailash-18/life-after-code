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

