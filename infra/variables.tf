variable "project_id" {
  description = "Google Cloud Project ID for Project Sentinel"
  type        = string
  default     = "project-sentinel-hackathon"
}

variable "region" {
  description = "Default GCP Region for Cloud Run & Artifact Registry"
  type        = string
  default     = "us-central1"
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
  description = "Default container image for the Sentinel Target App"
  type        = string
  default     = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/target-app:stable"
}

variable "backend_image" {
  description = "Default container image for the Sentinel Backend API"
  type        = string
  default     = "us-central1-docker.pkg.dev/project-sentinel-hackathon/sentinel/backend:latest"
}
