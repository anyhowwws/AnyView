resource "google_cloud_run_v2_service" "api" {
  name     = "anyview-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0 # scale to zero; cold starts are acceptable for a single-user tool
      max_instance_count = var.api_max_instances
    }

    containers {
      # Placeholder so the service exists before CI has pushed a real image.
      # CI owns the image from then on — see lifecycle below.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true # bill CPU only while handling requests
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_REGION"
        value = var.vertex_region
      }
      env {
        name  = "CLAUDE_MODEL"
        value = var.claude_model
      }
    }

    # Interviews stream for up to a few minutes; default 300s is fine, stated explicitly.
    timeout = "300s"
  }

  lifecycle {
    # Terraform sets the service up; GitHub Actions deploys images. Without this,
    # every plan would try to roll the image back to the placeholder.
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_project_service.enabled]
}

# Firebase Hosting rewrites reach Cloud Run as an unauthenticated caller, so the
# service must be publicly invokable. User auth is enforced inside the app
# (Identity Platform, Phase 1), not at the invoker layer.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
