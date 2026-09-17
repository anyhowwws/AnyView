# Uploaded resumes (ADR 0010). One bucket, one prefix per user (uploads/<uid>/),
# written by the browser through short-lived signed URLs and read by the API.
# These objects are the raw material Phase 2's RawDump provenance points at,
# so nothing here expires them.

resource "google_storage_bucket" "uploads" {
  name     = "${var.project_id}-uploads"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # A re-upload gets a new object name, so there is nothing for versioning to keep.
  versioning {
    enabled = false
  }

  # The browser PUTs directly to the bucket from the app's origins.
  cors {
    origin          = concat(var.cors_origins, ["http://localhost:3000"])
    method          = ["PUT"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.enabled]
}

# The API reads uploads and (later) writes derived objects — scoped to this bucket.
resource "google_storage_bucket_iam_member" "api_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.api.member
}

# Signed URLs need a signature. Cloud Run credentials carry no private key, so
# the API asks the IAM signBlob API to sign as its own service account — which
# requires the SA to hold tokenCreator on itself. Scoped to the one SA.
resource "google_service_account_iam_member" "api_signs_as_itself" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_service_account.api.member
}

# Developers running the API locally sign as the same SA through their own ADC,
# which needs this grant explicitly: roles/owner does not carry signBlob.
resource "google_service_account_iam_member" "local_signers" {
  for_each           = toset(var.local_signers)
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}
