# anyview.anyapps.cloud → Firebase Hosting (ADR 0008).
#
# Firebase registers the domain on the Hosting site and tells us which DNS
# records it needs — a CNAME to the site and a TXT for the certificate
# challenge, the same two AnyTatt has. Those records are written into the
# Route 53 zone below in the same apply.
#
# The record *values* only exist once Firebase has issued them, so the Route 53
# resources use a fixed `count` (values may be unknown at plan time; keys may
# not) rather than `for_each`. A precondition fails the apply with a clear
# message if Firebase ever asks for a different number of records.

resource "google_firebase_hosting_custom_domain" "app" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id # the default Hosting site shares the project id

  custom_domain   = var.app_domain
  cert_preference = "GROUPED" # shared cert, free; DEDICATED costs and buys nothing here

  # Don't block the apply on propagation; the records are created right after.
  wait_dns_verification = false

  depends_on = [google_firebase_project.this]
}

data "aws_route53_zone" "root" {
  name = "${var.dns_zone_name}."
}

locals {
  # Flatten Firebase's "please add these" list into one record per (type, name),
  # sorted so count.index is stable across applies. Only ADD actions; anything
  # else is Firebase reporting on records it found.
  dns_records_by_key = {
    for r in flatten([
      for u in google_firebase_hosting_custom_domain.app.required_dns_updates : [
        for d in u.desired : d.records
      ]
    ]) : "${r.type}:${r.domain_name}" => r if r.required_action == "ADD"
  }
  dns_records = [for k in sort(keys(local.dns_records_by_key)) : local.dns_records_by_key[k]]
}

resource "aws_route53_record" "app" {
  count = var.dns_record_count

  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.dns_records[count.index].domain_name
  type    = local.dns_records[count.index].type
  ttl     = 300
  # Route 53 wants TXT values quoted; Firebase hands them over bare.
  records = [
    local.dns_records[count.index].type == "TXT" && !startswith(local.dns_records[count.index].rdata, "\"")
    ? "\"${local.dns_records[count.index].rdata}\""
    : local.dns_records[count.index].rdata
  ]

  lifecycle {
    precondition {
      condition     = length(local.dns_records) == var.dns_record_count
      error_message = "Firebase asked for ${length(local.dns_records)} DNS record(s) but dns_record_count is ${var.dns_record_count}. Set dns_record_count to match and apply again."
    }
  }
}
