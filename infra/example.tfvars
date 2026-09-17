# Copy to terraform.tfvars (git-ignored) and fill in.
project_id         = "your-gcp-project-id"
region             = "us-central1"
vertex_region      = "global"
github_repo        = "anyhowwws/AnyView"
billing_account_id = "XXXXXX-XXXXXX-XXXXXX"
budget_amount      = 50
budget_currency    = "SGD"                    # must match the billing account
allowed_emails     = ["you@example.com"]      # Google accounts allowed to sign in
local_signers      = ["user:you@example.com"] # sign upload URLs locally; omit in CI
db_owner_iam_user  = "you@example.com"        # IAM database login from your laptop
