# Terraform run by GitHub Actions (ADR 0024). Two identities, split by what they
# can change, so a pull request can show a plan without being able to apply one.
#
#   anyview-tf-plan   read-only. Any workflow in this repository may use it, so
#                     it runs on pull requests.
#   anyview-tf-apply  owner. Only workflows running on `main` may use it.
#
# Both are reached through the same WIF pool as the deploy SA (github_wif.tf).
# No keys exist.

locals {
  # The state bucket is created by infra/bootstrap, outside this stack, so it is
  # named rather than referenced.
  tfstate_bucket = "${var.project_id}-tfstate"

  # What GitHub puts in the OIDC `sub` claim for a job running on main. A pull
  # request job gets `repo:<repo>:pull_request` and a job on any other branch gets
  # that branch's ref, so neither can impersonate the apply SA.
  apply_subject = "repo:${var.github_repo}:ref:refs/heads/main"
}

# --- Plan: read-only ----------------------------------------------------------

resource "google_service_account" "tf_plan" {
  account_id   = "anyview-tf-plan"
  display_name = "AnyView Terraform plan (read-only)"
  description  = "Impersonated by GitHub Actions on pull requests and main to run terraform plan. Reads; changes nothing."
}

# viewer + securityReviewer is what a refresh needs to read every resource and
# its IAM policy. Both are project-level because reads have no narrower scope.
resource "google_project_iam_member" "tf_plan_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = google_service_account.tf_plan.member
}

resource "google_project_iam_member" "tf_plan_iam_reader" {
  project = var.project_id
  role    = "roles/iam.securityReviewer"
  member  = google_service_account.tf_plan.member
}

# The google provider sends calls with user_project_override, which needs this.
# Project-level: serviceusage has no per-resource form.
resource "google_project_iam_member" "tf_plan_quota" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = google_service_account.tf_plan.member
}

# Plans run with -lock=false, so reading the state is all it needs of the bucket.
resource "google_storage_bucket_iam_member" "tf_plan_state" {
  bucket = local.tfstate_bucket
  role   = "roles/storage.objectViewer"
  member = google_service_account.tf_plan.member
}

# On main the plan is saved to plans/<sha>.tfplan for the apply job. objectCreator
# cannot overwrite or delete, and the condition keeps it out of the state prefix.
resource "google_storage_bucket_iam_member" "tf_plan_save" {
  bucket = local.tfstate_bucket
  role   = "roles/storage.objectCreator"
  member = google_service_account.tf_plan.member

  condition {
    title      = "plans-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${local.tfstate_bucket}/objects/plans/\")"
  }
}

# Refreshing the budget reads it from the billing account.
resource "google_billing_account_iam_member" "tf_plan_budget" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.viewer"
  member             = google_service_account.tf_plan.member

  # Setting a billing account's IAM policy goes through the Cloud Billing API,
  # which has to be enabled on the project first.
  depends_on = [google_project_service.enabled["cloudbilling.googleapis.com"]]
}

resource "google_service_account_iam_member" "tf_plan_impersonate" {
  service_account_id = google_service_account.tf_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# --- Apply: owner, from main only ---------------------------------------------

resource "google_service_account" "tf_apply" {
  account_id   = "anyview-tf-apply"
  display_name = "AnyView Terraform apply"
  description  = "Impersonated by workflows running on main to run terraform apply. Can change anything in the project."
}

# Owner, at project level, because nothing narrower exists for this job: the
# stack creates IAM bindings, service accounts and Cloud SQL, and anything that
# can edit IAM can already grant itself every other role. Listing admin roles
# one by one would look tighter and be no tighter. The guard is who may become
# this identity (below), not what it holds.
resource "google_project_iam_member" "tf_apply_owner" {
  project = var.project_id
  role    = "roles/owner"
  member  = google_service_account.tf_apply.member
}

# The budget lives on the billing account, which project roles do not reach.
# costsManager is the narrowest role that can create and change budgets.
resource "google_billing_account_iam_member" "tf_apply_budget" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.costsManager"
  member             = google_service_account.tf_apply.member

  depends_on = [google_project_service.enabled["cloudbilling.googleapis.com"]]
}

# One exact subject, not a repository-wide set: only a job running on `main` gets
# this identity (ADR 0024). The repository is private on GitHub Free, which has no
# branch protection and no environment approvals, so who can push to main is the
# real control.
resource "google_service_account_iam_member" "tf_apply_impersonate" {
  service_account_id = google_service_account.tf_apply.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/${local.apply_subject}"
}
