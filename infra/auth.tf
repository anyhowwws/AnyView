# Sign-in: Google accounts through Identity Platform (Firebase Authentication),
# allow-listed by email in the API (ADR 0009).
#
# Split of ownership, copied from AnyTatt where it proved out:
#   - Terraform owns the Identity Platform config, the authorized domains, and
#     the Firebase web app whose public config the frontend is built with.
#   - The Firebase CLI provisions the Google OAuth client from
#     ../firebase-auth.json (one-time owner command, see README). That keeps
#     the OAuth client secret out of state and out of the repository.

resource "google_identity_platform_config" "default" {
  project = var.project_id

  autodelete_anonymous_users = true
  sign_in {
    anonymous { enabled = false }
  }

  # Where a sign-in may start from. Firebase Hosting serves the auth handler
  # (/__/auth/handler) on the custom domain, so it is the production authDomain.
  authorized_domains = [
    "localhost",
    var.app_domain,
    "${var.project_id}.web.app",
    "${var.project_id}.firebaseapp.com",
  ]

  depends_on = [google_project_service.enabled, google_firebase_project.this]
}

# The web app registration gives us the Firebase client config, including an
# API key with exactly the restrictions Firebase's hosted sign-in handler
# expects. AnyTatt learned that a hand-made, narrower key cannot load that
# handler; this avoids the problem instead of working around it.
resource "google_firebase_web_app" "app" {
  provider     = google-beta
  project      = var.project_id
  display_name = "AnyView web"

  # Keep the registration if the resource is ever removed from Terraform;
  # deleting it would rotate the public config out from under a live build.
  deletion_policy = "ABANDON"

  depends_on = [google_firebase_project.this]
}

data "google_firebase_web_app_config" "app" {
  provider   = google-beta
  project    = var.project_id
  web_app_id = google_firebase_web_app.app.app_id
}
