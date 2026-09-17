# Cloud SQL for PostgreSQL + pgvector (ADR 0002, 0011).
#
# Access model: the API and the owner log in with IAM database authentication
# — no database password exists for the application. The one password that
# has to exist (the built-in `postgres` user, the only role Cloud SQL lets
# create extensions) is generated ephemerally, written once to Secret Manager
# and to the user with write-only arguments, and never enters Terraform state.

resource "google_sql_database_instance" "main" {
  name             = "anyview-pg"
  database_version = "POSTGRES_17"
  region           = var.region

  # Guard the data, not the budget: a `terraform destroy` must be a decision.
  deletion_protection = true

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL" # single zone, no HA (brief)
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true
    edition           = "ENTERPRISE"

    ip_configuration {
      # Public IP with no authorized networks: nothing can connect directly.
      # The Cloud SQL connector reaches it through the admin API with TLS and
      # IAM, which is the only path the app and the owner use. Private IP
      # would need a VPC connector for Cloud Run — cost and scope for no gain.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "18:00" # 02:00 SGT
      point_in_time_recovery_enabled = false   # binary logs cost storage; daily is enough for now
      backup_retention_settings {
        retained_backups = 7
      }
    }

    maintenance_window {
      day          = 7  # Sunday
      hour         = 19 # 03:00 SGT
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "anyview" {
  name     = "anyview"
  instance = google_sql_database_instance.main.name
}

# --- Who can log in --------------------------------------------------------

locals {
  # Cloud SQL names IAM service-account users without the ".gserviceaccount.com" suffix.
  db_api_user = trimsuffix(google_service_account.api.email, ".gserviceaccount.com")
}

resource "google_sql_user" "api" {
  name     = local.db_api_user
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_user" "owner" {
  name     = var.db_owner_iam_user
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_USER"
}

# IAM login needs two project-level roles (there is no per-instance IAM):
# cloudsql.client to open the connection, cloudsql.instanceUser to log in.
resource "google_project_iam_member" "api_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.api.member
}

resource "google_project_iam_member" "api_cloudsql_login" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = google_service_account.api.member
}

# --- The one password: postgres, for bootstrap and break-glass only ----------

# Regenerated on every run but only *written* when db_password_version changes
# (write-only arguments send their value once per version). Never in state.
ephemeral "random_password" "postgres" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "postgres_password" {
  secret_id = "anyview-postgres-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "postgres_password" {
  secret                 = google_secret_manager_secret.postgres_password.id
  secret_data_wo         = ephemeral.random_password.postgres.result
  secret_data_wo_version = var.db_password_version
}

resource "google_sql_user" "postgres" {
  name                = "postgres"
  instance            = google_sql_database_instance.main.name
  password_wo         = ephemeral.random_password.postgres.result
  password_wo_version = var.db_password_version
  # Both writes happen in the same run, from the same ephemeral value.
  depends_on = [google_secret_manager_secret_version.postgres_password]
}
