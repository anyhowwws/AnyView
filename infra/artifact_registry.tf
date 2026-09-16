resource "google_artifact_registry_repository" "api" {
  repository_id = "anyview"
  location      = var.region
  format        = "DOCKER"
  description   = "AnyView API container images"

  # Keep only recent images; every CI run pushes one.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.enabled]
}
