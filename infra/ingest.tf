# Queued ingestion (ADR 0034).
#
#   browser ──POST /brain/jobs──▶ anyview-api ──create task──▶ Cloud Tasks queue
#                                                                   │ OIDC token as anyview-tasks
#   browser ◀─GET /brain/jobs/{id}─ anyview-api                      ▼
#                       ▲                                    anyview-worker (private)
#                       └──────────── ingest_jobs (Cloud SQL) ◀──────┘
#
# The API never runs a resume through the model inside a request any more. It
# writes a job row, hands the id to the queue and answers 202. Cloud Tasks
# delivers the id to the worker and retries with backoff until the worker
# answers 2xx. The browser polls the row.

# --- The queue -----------------------------------------------------------------

resource "google_cloud_tasks_queue" "ingest" {
  # A deleted queue's name cannot be reused for about a week. Rename rather
  # than destroy-and-recreate.
  name     = "anyview-ingest"
  location = var.region

  rate_limits {
    # Each job is several model calls in parallel (ADR 0019). Two at once is
    # plenty for a handful of users and keeps Agent Platform quota and the worker's
    # one instance comfortable.
    max_concurrent_dispatches = 2
    max_dispatches_per_second = 1
  }

  retry_config {
    # The worker reads the same number (INGEST_MAX_ATTEMPTS) so that it fails
    # the job on the last attempt instead of asking for a retry nobody sends.
    max_attempts = var.ingest_max_attempts
    # 15 s, 30 s, 60 s, 120 s: by the fifth attempt 225 s have passed, longer
    # than the worker's 120 s lease, so a delivery that died mid-job (its row
    # still says running) is taken over by a later one (brain/ingest.py:LEASE).
    min_backoff   = "15s"
    max_backoff   = "240s"
    max_doublings = 4
  }

  # Every dispatch and its outcome in Cloud Logging. At this volume the cost
  # is nothing, and it is the only record of a delivery the worker never saw.
  stackdriver_logging_config {
    sampling_ratio = 1.0
  }

  depends_on = [google_project_service.enabled]
}

# --- Who Cloud Tasks is when it calls the worker -------------------------------

resource "google_service_account" "tasks" {
  account_id   = "anyview-tasks"
  display_name = "AnyView Cloud Tasks invoker"
  description  = "Identity Cloud Tasks signs its OIDC token as when it delivers an ingest job. Can invoke the worker service. Nothing else."
}

# The only grant that lets anything call the worker.
resource "google_cloud_run_v2_service_iam_member" "tasks_invoke_worker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.invoker"
  member   = google_service_account.tasks.member
}

# The API creates tasks on this one queue (cloudtasks.tasks.create), nothing more.
resource "google_cloud_tasks_queue_iam_member" "api_enqueue" {
  name     = google_cloud_tasks_queue.ingest.name
  location = google_cloud_tasks_queue.ingest.location
  role     = "roles/cloudtasks.enqueuer"
  member   = google_service_account.api.member
}

# A task that carries an OIDC token for anyview-tasks may only be created by
# someone allowed to act as anyview-tasks. Scoped to that one account.
resource "google_service_account_iam_member" "api_acts_as_tasks" {
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.api.member
}

# --- The worker ----------------------------------------------------------------

resource "google_cloud_run_v2_service" "worker" {
  name     = "anyview-worker"
  location = var.region
  # Two locks. Ingress: only requests from inside Google Cloud in this project
  # reach the service at all; Cloud Tasks is one of the sources Cloud Run counts
  # as internal. IAM: of those, only anyview-tasks holds run.invoker. There is
  # no allUsers binding, so neither the browser nor the internet can call it.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    # The API's identity, deliberately (ADR 0034): the worker needs exactly the
    # API's data access (Agent Platform, the uploads bucket, the same Cloud SQL IAM
    # user). A second runtime account would be a second database user with the
    # same grants, for no reduction in what either can reach.
    service_account = google_service_account.api.email

    scaling {
      # Unlike the API (ADR 0023), scale-to-zero is right here: a cold start
      # delays a queued job by a minute, and nobody's request is waiting on it.
      min_instance_count = 0
      # One instance bounds the Cloud SQL connections (ADR 0011): the API's
      # pool plus this one stays far inside db-g1-small's limit.
      max_instance_count = 1
    }
    # The queue sends at most two at once; a little headroom for a duplicate
    # delivery, which the job's claim turns away.
    max_instance_request_concurrency = 4

    containers {
      # Same placeholder and same CI ownership of the image as the API.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # The job runs inside the request Cloud Tasks makes, so request-based
        # CPU is enough: nothing runs after the response.
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = merge(local.runtime_env, {
          APP_MODULE          = "anyview.worker:app" # backend/Dockerfile
          INGEST_MAX_ATTEMPTS = tostring(var.ingest_max_attempts)
        })
        content {
          name  = env.key
          value = env.value
        }
      }
    }

    # Cloud Tasks waits this long for an answer (tasks.py: DISPATCH_DEADLINE).
    # A resume takes about 90 s.
    timeout = "600s"
  }

  lifecycle {
    # As for the API (cloud_run.tf): CI owns the image.
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      scaling,
    ]
  }

  depends_on = [google_project_service.enabled]
}

# CI deploys the image to the worker too — scoped to the one service. It
# already holds actAs on the API's account, which the worker runs as.
resource "google_cloud_run_v2_service_iam_member" "deploy_worker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.developer"
  member   = google_service_account.deploy.member
}
