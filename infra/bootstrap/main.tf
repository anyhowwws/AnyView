# Bootstrap: the one thing that has to exist before the main stack can store
# its state. Run once with local state; the resulting bucket name is passed to
# `terraform init -backend-config` in ../.
#
#   terraform init && terraform apply
#
# The local terraform.tfstate here is git-ignored and only ever describes this
# single bucket. Losing it is recoverable with `terraform import`.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  description = "GCP project that will hold all AnyView resources."
  type        = string
}

variable "region" {
  description = "Region for the state bucket."
  type        = string
  default     = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_id}-tfstate"
  location = var.region

  # Bucket-level IAM only; no per-object ACLs to reason about.
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Keep prior state versions so a bad apply can be rolled back.
  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.storage]
}

output "state_bucket" {
  value       = google_storage_bucket.tfstate.name
  description = "Pass as -backend-config=\"bucket=...\" when initialising ../"
}
