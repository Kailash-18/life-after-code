terraform {
  required_version = ">= 1.5.0"

  # Production-Grade Remote State Storage in AWS S3 with Distributed DynamoDB Locking
  # Supports partial configuration via -backend-config=backend_config/<env>.s3.tfbackend
  backend "s3" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.30"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}


provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "aws" {
  region = var.aws_state_region

  default_tags {
    tags = {
      Project     = "Project-Sentinel"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Security    = "ZeroTrust-StateProtection"
    }
  }
}

