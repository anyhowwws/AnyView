# Every API the stack touches, enabled explicitly. disable_on_destroy = false so
# a `terraform destroy` doesn't also switch off APIs other things may rely on.
locals {
  services = [
    "run.googleapis.com",                  # Cloud Run
    "artifactregistry.googleapis.com",     # container images
    "aiplatform.googleapis.com",           # Vertex AI (Claude + embeddings)
    "iam.googleapis.com",                  # service accounts
    "iamcredentials.googleapis.com",       # WIF token exchange
    "sts.googleapis.com",                  # WIF token exchange
    "cloudresourcemanager.googleapis.com", # project-level IAM
    "billingbudgets.googleapis.com",       # budget alert
    "secretmanager.googleapis.com",        # secrets (Phase 1+; the API, not any value)
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "firebase.googleapis.com", # Firebase Hosting
    "firebasehosting.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}
