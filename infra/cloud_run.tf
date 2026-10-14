# What both services built from the API image need to run the app: the model,
# the database and the upload bucket. The worker (ingest.tf) takes these and
# nothing else; the API adds what only a browser-facing service needs.
locals {
  runtime_env = {
    GOOGLE_CLOUD_PROJECT = var.project_id
    VERTEX_REGION        = var.vertex_region
    MODEL_ID             = var.model_id
    MODEL_ID_FAST        = var.fast_model_id
    TTS_MODEL_ID         = var.tts_model_id
    HARVEY_VOICE         = var.harvey_voice
    DONNA_VOICE          = var.donna_voice
    LIVE_MODEL_ID        = var.live_model_id
    LIVE_REGION          = var.live_region
    UPLOAD_BUCKET        = google_storage_bucket.uploads.name
    DB_INSTANCE          = google_sql_database_instance.main.connection_name
    DB_NAME              = google_sql_database.anyview.name
    DB_IAM_USER          = local.db_api_user
  }

  api_env = {
    CORS_ORIGINS   = join(",", var.cors_origins)
    ALLOWED_EMAILS = join(",", var.allowed_emails)
    # Queued ingestion (ADR 0034): where the API puts a job, who Cloud Tasks
    # calls with it, and as whom.
    TASKS_QUEUE   = google_cloud_tasks_queue.ingest.id
    WORKER_URL    = google_cloud_run_v2_service.worker.uri
    TASKS_INVOKER = google_service_account.tasks.email
  }
}

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

      # The shared runtime settings, then the API's own (locals above).
      dynamic "env" {
        for_each = merge(local.runtime_env, local.api_env)
        content {
          name  = env.key
          value = env.value
        }
      }
    }

    # A WebSocket counts as one request for as long as it is open. A Live question
    # (ADR 0031) runs up to its clock (≤ 300 s) plus follow-ups, and the API caps
    # it at nine minutes, inside Live's own ten-minute connection limit.
    timeout = "600s"
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
