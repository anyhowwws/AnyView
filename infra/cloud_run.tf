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
        name  = "MODEL_ID"
        value = var.model_id
      }
      env {
        name  = "MODEL_ID_FAST"
        value = var.fast_model_id
      }
      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.cors_origins)
      }
    }

    # Interviews stream for up to a few minutes; default 300s is fine, stated explicitly.
    timeout = "300s"
  }

  lifecycle {
    # Terraform sets the service up; GitHub Actions deploys images. Without this,
    # every plan would try to roll the image back to the placeholder. The
    # service-level `scaling` block is API-populated defaults (all zero) that the
    # provider reports as a change on every plan; the real scaling lives in
    # template.scaling above.
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      scaling,
    ]
  }

  depends_on = [google_project_service.enabled]
}

# Phase 0: no public invoker binding. The service is reachable only by callers
# with roles/run.invoker (the owner, via `gcloud run services proxy`). A public
# binding arrives together with app-level auth (Identity Platform, Phase 1) —
# an open, unauthenticated LLM endpoint is a cost trap, and the budget only
# alerts, it does not stop spend. See ADR 0006.
