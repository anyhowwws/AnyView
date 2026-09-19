# 0008 — Custom domain on Firebase Hosting, DNS records managed in Route 53

- **Status:** Accepted, amended by 0012
- **Date:** 2026-09-18

## Context

The product should live at `anyview.anyapps.cloud`. The `anyapps.cloud` zone is
hosted in AWS Route 53 alongside the owner's other projects (AnyTatt is at
`anytatt.anyapps.cloud` the same way: a CNAME to its Firebase Hosting site plus
a TXT record for the certificate challenge). Moving the zone to Cloud DNS for
one subdomain is not on the table.

The brief's rule is that if a resource exists, it exists in `.tf`. AnyTatt's
records were added by hand in the Route 53 console; that is the thing to avoid
repeating.

## Options considered

**Console on both sides.** Register the domain in the Firebase console, copy
the two records into Route 53 by hand. What AnyTatt did. Works, and leaves two
resources nobody can rebuild from the repo.

**Terraform for Firebase, Route 53 by hand.** Halves the problem. The record
values still live only in a console.

**Terraform on both sides.** `google_firebase_hosting_custom_domain` registers
the domain; `aws_route53_record` writes the CNAME. Adds a second provider to a
stack that is otherwise pure GCP, and needs AWS credentials wherever the stack
is applied.

## Decision

Terraform on both sides. The AWS provider manages **only** Route 53 records in
this repository; no compute, storage, or IAM on AWS. Credentials are the
owner's local `aws login` session — the stack is applied from the laptop, not
from CI, and there is no AWS identity in GitHub.

One record: a CNAME from the domain to the default Hosting site
(`anyapps-anyview.web.app`). It is written statically — the site hostname is
deterministic — rather than derived from what Firebase reports back. Firebase's
`required_dns_updates` / `cert.verification` lists are transient (a record
leaves "desired" once discovered) and the certificate challenge completes over
HTTP through the CNAME, so the `_acme-challenge` TXT the console suggests is
not needed; AnyTatt's is a leftover of the console flow. A first attempt at
driving `aws_route53_record` from those lists would have deleted the CNAME on
the second apply; they now feed a diagnostic output only.

The Cloud Run API keeps its `*.run.app` URL and is reached cross-origin (ADR 0006),
so `cors_origins` gains the custom domain. Identity Platform (Phase 1) will
list it as an authorized domain.

## What this costs

- **If Firebase ever needs the DNS challenge** (HTTP verification blocked,
  for instance), the TXT it wants appears in the `firebase_dns_requests`
  output and is added by hand or as a second static record. Not automated on
  purpose: the value is transient and the case has not occurred.
- **Two clouds' credentials to apply.** `gcloud auth application-default login`
  and `aws login` both need to be live. Documented in the README.
- **Certificate provisioning is Firebase's timeline.** Typically minutes after
  the records propagate, occasionally longer; `wait_dns_verification = false`
  keeps Terraform from hanging on it. `host_state` / `ownership_state` on the
  resource report progress.
- **Two-provider version drift.** Both are pinned to a major; lock file is
  git-ignored like the rest of the state, so `terraform init` refreshes it.
