# Enables Firebase on the project so Hosting can be used. The default Hosting
# site (id = project id) is created by Firebase when the project is enabled;
# `firebase deploy` in CI targets it.
resource "google_firebase_project" "this" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.enabled]
}
