# anyview.anyapps.cloud → Firebase Hosting (ADR 0008).
#
# This resource registers the domain and drives certificate provisioning.
# The DNS record that actually points the domain here — a CNAME in Route 53 —
# lives in the separate infra/dns stack (ADR 0012), so this stack never needs
# AWS credentials. Nothing here reads anything back from that stack: the CNAME
# target (`<site_id>.web.app`) is Firebase Hosting's deterministic default and
# is written statically over there from var.project_id, matching this
# resource's `site_id` below.
#
# What Firebase reports back (`required_dns_updates`, `cert.verification`) is
# transient: a record disappears from "desired" the moment Firebase discovers
# it, and the certificate challenge is completed over HTTP through the CNAME
# (observed: `cert.verification.http.discovered` matched `desired` within
# minutes; the `_acme-challenge` TXT was never needed). Driving resources from
# that list would delete the CNAME on the next apply, so it only feeds the
# `firebase_dns_requests` output for troubleshooting.

resource "google_firebase_hosting_custom_domain" "app" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id # the default Hosting site shares the project id

  custom_domain   = var.app_domain
  cert_preference = "GROUPED" # shared cert, free; DEDICATED costs and buys nothing here

  # Don't block the apply on propagation; infra/dns applies the CNAME separately.
  wait_dns_verification = false

  depends_on = [google_firebase_project.this]
}
