# anyview.anyapps.cloud → Firebase Hosting (ADR 0008).
#
# Firebase registers the domain on the Hosting site; Route 53 gets one CNAME
# pointing the domain at the site. That record is deterministic — the site's
# default hostname is `<site_id>.web.app` — so it is written statically and
# does not depend on anything Firebase reports back.
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

  # Don't block the apply on propagation; the CNAME is created right after.
  wait_dns_verification = false

  depends_on = [google_firebase_project.this]
}

data "aws_route53_zone" "root" {
  name = "${var.dns_zone_name}."
}

resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = var.app_domain
  type    = "CNAME"
  ttl     = 300
  records = ["${google_firebase_hosting_custom_domain.app.site_id}.web.app"]
}
