output "api_url" {
  description = "Cloud Run service URL (Firebase Hosting rewrites /api/** here)."
  value       = google_cloud_run_v2_service.api.uri
}

output "artifact_registry" {
  description = "Image path prefix for docker push."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

# The next three go into GitHub repository *variables* (not secrets — none are sensitive).
output "wif_provider" {
  description = "Set as GitHub variable GCP_WIF_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_service_account" {
  description = "Set as GitHub variable GCP_DEPLOY_SA."
  value       = google_service_account.deploy.email
}

output "project_id" {
  description = "Set as GitHub variable GCP_PROJECT_ID."
  value       = var.project_id
}

output "app_url" {
  description = "The frontend on its custom domain (ADR 0008)."
  value       = "https://${var.app_domain}"
}

output "firebase_dns_requests" {
  description = "Records Firebase still wants for the custom domain (empty once verified). Diagnostic only."
  value = [
    for r in flatten([
      for u in google_firebase_hosting_custom_domain.app.required_dns_updates : [
        for d in u.desired : d.records
      ]
    ]) : "${r.type} ${r.domain_name} ${r.rdata}" if r.required_action == "ADD"
  ]
}

# Public by design (it identifies the project to Google's sign-in service; it
# is not a credential). Goes into GitHub repository variables for the build.
output "firebase_web_config" {
  description = "Set as NEXT_PUBLIC_FIREBASE_API_KEY / _AUTH_DOMAIN / _PROJECT_ID for the frontend build."
  value = {
    api_key     = data.google_firebase_web_app_config.app.api_key
    auth_domain = var.app_domain # Hosting serves /__/auth/handler on the custom domain
    project_id  = var.project_id
  }
}

output "upload_bucket" {
  description = "Where uploaded resumes land (uploads/<uid>/…)."
  value       = google_storage_bucket.uploads.name
}

output "db_instance" {
  description = "Cloud SQL connection name (project:region:instance) for the connector."
  value       = google_sql_database_instance.main.connection_name
}

output "db_iam_user" {
  description = "The API's IAM database user name."
  value       = local.db_api_user
}
