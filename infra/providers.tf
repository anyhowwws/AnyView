terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    # Ephemeral random_password for the one database password (ADR 0011).
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # Some APIs (Billing Budgets among them) bill quota to the *caller's* project,
  # and user ADC has none set by default — the call fails with 403
  # SERVICE_DISABLED against Google's SDK project. Send this project as the
  # quota project instead. Needs serviceusage.services.use, which owner has.
  user_project_override = true
  billing_project       = var.project_id
}

# Firebase resources are only in the beta provider.
provider "google-beta" {
  project = var.project_id
  region  = var.region

  user_project_override = true
  billing_project       = var.project_id
}
