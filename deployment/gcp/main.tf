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

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_kms_key_ring" "main" {
  name     = "${var.name_prefix}-keyring"
  location = var.region
}

resource "google_kms_crypto_key" "registry" {
  name            = "${var.name_prefix}-registry"
  key_ring        = google_kms_key_ring.main.id
  rotation_period = "7776000s" # 90 days
}

# Artifact Registry service agent must be able to use the key.
resource "google_kms_crypto_key_iam_member" "registry" {
  crypto_key_id = google_kms_crypto_key.registry.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-artifactregistry.iam.gserviceaccount.com"
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "${var.name_prefix}-images"
  format        = "DOCKER"
  location      = var.region
  kms_key_name  = google_kms_crypto_key.registry.id
  depends_on    = [google_kms_crypto_key_iam_member.registry]
}

resource "google_secret_manager_secret" "jwt" {
  secret_id = "${var.name_prefix}-jwt-secret"
  replication {
    auto {}
  }
}

# Cloud Run services, networking and Memorystore are the next increment (see docs).
