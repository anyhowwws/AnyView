# 0024 — Terraform plan on pull requests, automatic apply on main

- **Status:** Accepted
- **Date:** 2026-10-13
- **Amends:** brief ("Terraform runs by hand"), `.claude/settings.json` ("terraform apply is a user action")

## Context

CI only ran `terraform fmt` and `validate`. Plans and applies happened on a laptop,
so a change to `infra/` was reviewed as code but never as its effect, and the state
of production depended on whoever last ran `apply` from where. The deploy identity
(`anyview-deploy`) cannot apply: it pushes images and updates one Cloud Run service.

The repository is private on GitHub Free. That plan has no branch protection and no
Environments with required reviewers, so a "click to approve" gate is not available.

## Options considered

**Keep applying by hand.** Nothing new to trust. But the plan stays invisible
during review and "what is deployed" depends on a laptop.

**Plan on PRs, apply on main behind an approved Environment.** The strongest gate:
a human approves the exact plan before anything changes. Needs a public repository
or GitHub Pro. Planned for when the repository goes public.

**Plan on PRs, apply automatically on main.** Works on Free. The gate is the review
of the PR and its plan comment, and what is allowed to run on `main`.

## Decision

The third, for now. The Environment version is the intended end state once the
repository is public; it is a small change (add `environment:` to the apply job and
move the apply identity's trust to that subject).

- **Two identities** (`infra/terraform_ci.tf`), both through the existing WIF pool:
  - `anyview-tf-plan`: viewer + security reviewer, read on the state bucket, and
    create-only on `plans/` in it. Any workflow in this repository may use it.
  - `anyview-tf-apply`: owner. Only a workflow running on `main` may use it (the
    binding is on the exact subject `repo:<repo>:ref:refs/heads/main`, not the
    repository). A pull request gets a `pull_request` subject and cannot match it.
- **`terraform-plan`** runs on pull requests (same-repo only) and on pushes to main.
  On a PR it posts the plan as a comment. On main it saves the plan file to
  `gs://<project>-tfstate/plans/<sha>.tfplan`.
- **`terraform-apply`** runs on main only, only when the plan has changes. It applies
  the saved plan, not a new one. Terraform refuses a saved plan if the state moved in
  between.
- **`deploy-api` waits for the apply** (or for it to be skipped), so a release never
  runs ahead of the infrastructure it needs.
- `-lock=false` on plans: they change nothing, two PRs can plan at once, and the
  plan identity needs no write access to the state.
- Inputs come from `TF_VAR_*` set from repository variables, replacing the
  git-ignored `terraform.tfvars` in CI. Defaults cover the rest.
- `.terraform.lock.hcl` is now committed (with `linux_amd64` and `darwin_arm64`
  hashes), so the plan job and the apply job use the same provider builds.
- `billing_account_id` and `allowed_emails` are `sensitive`, so a plan comment does
  not print them (it matters most once the repository is public).
- The plan file lives in the private state bucket, not a workflow artifact, because
  artifacts of a public repository are downloadable by anyone signed in to GitHub.

## What this costs

- **An owner credential exists in GitHub, and nothing stands between a push to main
  and an apply.** With no branch protection, anyone with write access can push
  straight to `main` and change the project as owner. Fine while the owner is the
  only collaborator; it is the first thing to fix before anyone else gets write
  access (go public and add the Environment, or upgrade).
- **Review is the only check**, and it is not enforced. Read the plan comment before
  merging.
- **A PR can run its own Terraform code** with the read-only identity (`external`
  data sources, providers). Same-repo PRs only, so only collaborators; the identity
  cannot change anything.
- **Plan files pile up** in the state bucket on every main push with changes. The
  apply job removes its own; a failed or skipped run leaves one behind. They are tiny.
- **Bootstrapping is manual, once.** The identities cannot create themselves; the
  first `terraform apply` of this change runs from a laptop (see below).
- **Local applies still work and still race.** Nothing stops one; the state lock
  stops a simultaneous one. Prefer CI.
- **The AWS stack (`infra/dns`, ADR 0012) stays manual.** It has its own state,
  credentials and rare changes.

## Rollout

1. From a laptop: `terraform apply` on this branch (creates the two service accounts
   and their bindings). Merging first would fail: CI cannot use identities that do
   not exist yet.
2. Set repository variables: `GCP_TF_PLAN_SA`, `GCP_TF_APPLY_SA` (from
   `terraform output`), `TF_BILLING_ACCOUNT_ID`, `TF_DB_OWNER_IAM_USER`,
   `TF_ALLOWED_EMAILS` (JSON list), and `TF_LOCAL_SIGNERS` if laptop upload signing
   should survive (otherwise CI removes that binding).
3. Open a PR. The first plan must say **No changes**. If it does not, `terraform.tfvars`
   sets something that the variables above do not, and applying would change it.
