# Two identities, each with exactly the roles it needs. Project-level bindings
# are used only where the API offers nothing narrower; that is called out inline.

# --- Runtime identity: what the API is when it runs on Cloud Run --------------

resource "google_service_account" "api" {
  account_id   = "anyview-api"
  display_name = "AnyView API runtime"
  description  = "Identity of the Cloud Run service. Calls Gemini Enterprise Agent Platform; writes logs. Nothing else."
}

# Call Claude and embeddings on Gemini Enterprise Agent Platform (ADR 0004). This is the only model-access grant in the project.
# aiplatform.user is project-level by API design — Agent Platform has no per-model IAM.
resource "google_project_iam_member" "api_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = google_service_account.api.member
}

resource "google_project_iam_member" "api_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = google_service_account.api.member
}

# --- Deploy identity: what GitHub Actions is when it deploys -----------------

resource "google_service_account" "deploy" {
  account_id   = "anyview-deploy"
  display_name = "AnyView GitHub Actions deployer"
  description  = "Impersonated by GitHub Actions via WIF. Pushes images, updates the Cloud Run service, deploys Hosting."
}

# Push images — scoped to the one repository, not the project.
resource "google_artifact_registry_repository_iam_member" "deploy_push" {
  repository = google_artifact_registry_repository.api.name
  location   = google_artifact_registry_repository.api.location
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deploy.member
}

# Update the Cloud Run service — scoped to the one service.
resource "google_cloud_run_v2_service_iam_member" "deploy_run" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.developer"
  member   = google_service_account.deploy.member
}

# Deploying a revision that runs as the API SA requires actAs on that SA — scoped to the one SA.
resource "google_service_account_iam_member" "deploy_act_as_api" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deploy.member
}

# Firebase Hosting has no per-site IAM; project-level is the narrowest the API allows.
resource "google_project_iam_member" "deploy_hosting" {
  project = var.project_id
  role    = "roles/firebasehosting.admin"
  member  = google_service_account.deploy.member
}
