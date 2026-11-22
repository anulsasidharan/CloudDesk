# GCP scaffold: Artifact Registry + Cloud Run + Secret Manager + Cloud Logging.
# Status: written, NOT applied, NOT validated against a real project. Needs cloud credentials.
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
  backend "gcs" {} # configured with -backend-config=backend.hcl (git-ignored)
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "${var.name_prefix}-images"
  format        = "DOCKER"
  location      = var.region
}

resource "google_secret_manager_secret" "jwt" {
  secret_id = "${var.name_prefix}-jwt-secret"
  replication {
    auto {}
  }
}

# Cloud Run services, networking and Memorystore are the next increment (see docs).
