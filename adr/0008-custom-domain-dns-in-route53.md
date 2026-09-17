# 0008 — Custom domain on Firebase Hosting, DNS records managed in Route 53

- **Status:** Accepted
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
the domain and returns the records Firebase requires (`required_dns_updates`);
`aws_route53_record` writes them. Adds a second provider to a stack that is
otherwise pure GCP, and needs AWS credentials wherever the stack is applied.

## Decision

Terraform on both sides. The AWS provider manages **only** Route 53 records in
this repository; no compute, storage, or IAM on AWS. Credentials are the
owner's local `aws login` session — the stack is applied from the laptop, not
from CI, and there is no AWS identity in GitHub.

The CNAME points at the default Hosting site (`anyapps-anyview.web.app`); the
Cloud Run API keeps its `*.run.app` URL and is reached cross-origin (ADR 0006),
so `cors_origins` gains the custom domain. Identity Platform (Phase 1) will
list it as an authorized domain.

## What this costs

- **A fixed record count.** The record values are computed by Firebase, and
  `for_each` cannot iterate over keys unknown at plan time — that would force a
  two-step first apply. A fixed `count` (two records: CNAME + certificate TXT)
  keeps it to one apply; a precondition fails loudly if Firebase ever asks for
  a different number, and `dns_record_count` is the knob.
- **Two clouds' credentials to apply.** `gcloud auth application-default login`
  and `aws login` both need to be live. Documented in the README.
- **Certificate provisioning is Firebase's timeline.** Typically minutes after
  the records propagate, occasionally longer; `wait_dns_verification = false`
  keeps Terraform from hanging on it. `host_state` / `ownership_state` on the
  resource report progress.
- **Two-provider version drift.** Both are pinned to a major; lock file is
  git-ignored like the rest of the state, so `terraform init` refreshes it.
