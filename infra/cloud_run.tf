resource "google_cloud_run_v2_service" "api" {
  name     = "anyview-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email

    scaling {
      # One warm instance (ADR 0023). A cold start took ~66 s, and Cloud Run
      # refused requests outright while it booted.
      min_instance_count = 1
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
        cpu_idle          = true # bill CPU only while handling requests
        startup_cpu_boost = true # extra CPU while booting: imports + migrations (ADR 0023)
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
        name  = "TTS_MODEL_ID"
        value = var.tts_model_id
      }
      env {
        name  = "DONNA_VOICE"
        value = var.donna_voice
      }
      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.cors_origins)
      }
      env {
        name  = "ALLOWED_EMAILS"
        value = join(",", var.allowed_emails)
      }
      env {
        name  = "UPLOAD_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "DB_INSTANCE"
        value = google_sql_database_instance.main.connection_name
      }
      env {
        name  = "DB_NAME"
        value = google_sql_database.anyview.name
      }
      env {
        name  = "DB_IAM_USER"
        value = local.db_api_user
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

# The browser calls this service directly (ADR 0006), so the invoker must be
# public. Access control is app-level: every interview route requires a
# signed-in Google account on the ALLOWED_EMAILS list (ADR 0009). Phase 0 had
# no public binding because there was no app-level auth to stand behind it.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
