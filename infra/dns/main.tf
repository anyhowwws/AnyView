# anyview.anyapps.cloud → Firebase Hosting (ADR 0008, ADR 0012).
#
# The target hostname (`<site_id>.web.app`) is Firebase Hosting's deterministic
# default — it does not require reading anything back from the
# google_firebase_hosting_custom_domain resource, which lives in the main GCP
# stack. That's what makes this a genuinely separate stack rather than one
# needing a remote-state data source: nothing here depends on anything there.
#
# Firebase's `required_dns_updates` / `cert.verification` lists (surfaced as
# a diagnostic output in the main stack) are transient and were never needed
# for the certificate challenge, which completes over HTTP through this CNAME
# — see ADR 0008 for why there is no `_acme-challenge` TXT record here.

data "aws_route53_zone" "root" {
  name = "${var.dns_zone_name}."
}

resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = var.app_domain
  type    = "CNAME"
  ttl     = 300
  records = ["${var.hosting_site_id}.web.app"]
}
