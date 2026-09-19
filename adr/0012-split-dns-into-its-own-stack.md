# 0012 — Split the Route 53 DNS record into its own Terraform stack

- **Status:** Accepted
- **Date:** 2026-09-20

## Context

ADR 0008 put one AWS resource — the Route 53 CNAME for `anyview.anyapps.cloud`
— inside the main GCP stack, accepting "two clouds' credentials to apply" as
a stated cost. In practice that cost was worse than described: `terraform
plan`/`apply` refreshes *every* resource in a stack before doing anything
else, so a stale AWS session blocks the whole stack, not just the DNS record.
This actually happened: an unrelated Cloud SQL apply failed outright because
`aws login` had expired overnight, with no Cloud SQL changes involved at all.

## Options considered

**Leave it as one stack.** Keep both `aws login` and `gcloud auth
application-default login` fresh before any apply. Works, but the coupling is
real and will recur — the DNS record almost never changes, while GCP resources
change often as the product grows.

**Split into `infra/dns`, a separate Terraform root with its own state.**
Isolates the one AWS resource so only *its own* applies need AWS credentials.

## Decision

Split. `infra/dns` holds `provider "aws"`, the Route 53 zone data source, and
`aws_route53_record.app`, with its own state under a different prefix
(`anyview/dns`) in the same GCS bucket the main stack already uses. The
existing record was migrated with `terraform import`, not recreated — no DNS
change, no certificate re-provisioning, no downtime.

The split turned out to be free of cross-stack coupling: the CNAME's target
(`<project_id>.web.app`) is Firebase Hosting's deterministic default, so
`infra/dns` computes it from `var.project_id` directly rather than reading it
back from `google_firebase_hosting_custom_domain` in the main stack (which
stays there — it is a GCP resource and never needed AWS credentials in the
first place). Neither stack needs the other's state to plan or apply.

The main stack's `providers.tf` no longer declares the `aws` provider at all;
verified by running `terraform plan` there with deliberately invalid AWS
credentials and confirming no AWS calls are attempted.

## What this costs

- **Two `terraform apply` commands** instead of one, on the rare occasion the
  domain itself changes. `infra/dns/README.md` documents the two-line
  sequence.
- **A second state file to know about.** Same bucket, so no new credentials
  or bootstrap step — just a different `-chdir` or working directory.
- **Nothing else.** No resource depends on the other stack's output; this
  was a pure decoupling.
