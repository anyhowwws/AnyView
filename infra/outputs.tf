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

output "dns_records" {
  description = "What Firebase asked Route 53 to hold for the custom domain."
  value       = { for r in aws_route53_record.app : "${r.type} ${r.name}" => r.records }
}
