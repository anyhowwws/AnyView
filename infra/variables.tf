variable "project_id" {
  description = "GCP project that holds every AnyView resource."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Artifact Registry, and (later) Cloud SQL."
  type        = string
  default     = "us-central1"
}

variable "vertex_region" {
  description = "Gemini Enterprise Agent Platform location the model is served from. \"global\" is recommended for current-generation models; may differ from var.region."
  type        = string
  default     = "global"
}

variable "model_id" {
  description = "Gemini Enterprise Agent Platform model for judgement calls: plan, score, ideal (ADR 0007). A variable so a model change is a plan, not a code change."
  type        = string
  default     = "gemini-3.1-pro-preview"
}

variable "fast_model_id" {
  description = "Gemini Enterprise Agent Platform model for streamed interviewer turns, where time-to-first-token matters more than depth."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "tts_model_id" {
  description = "Gemini Enterprise Agent Platform model that speaks Harvey's questions in voice mode (ADR 0013). A text model cannot synthesise audio, so this is its own id."
  type        = string
  default     = "gemini-2.5-flash-preview-tts"
}

variable "live_model_id" {
  description = "Gemini Enterprise Agent Platform Live model that runs Harvey's spoken interview, follow-ups included (ADR 0031). Native-audio Live models are regional; confirm the id is enabled in Model Garden for the project before relying on it."
  type        = string
  default     = "gemini-3.8-live"
}

variable "live_region" {
  description = "Region the Live model is served from. Live models are not served from `global` (ADR 0031)."
  type        = string
  default     = "us-central1"
}

variable "harvey_voice" {
  description = "Prebuilt Agent Platform voice for Harvey, the interviewer. Male-sounding options include Charon (informative), Alnilam, Orus (firm), Puck (upbeat) and Fenrir (excitable). Alnilam read as British in a real run; the accent comes from the voice and the delivery direction together. Check a name with a real call before using it: an unknown one is a 400."
  type        = string
  default     = "Charon"
}

variable "donna_voice" {
  description = "Prebuilt Agent Platform voice for Donna, the Digital Garden's assistant, heard only in Discover's speak mode (ADR 0030). Female-sounding options include Kore (firm), Aoede (breezy), Leda (youthful), Zephyr (bright) and Sulafat (warm). Check a name with a real call before using it: an unknown one is a 400."
  type        = string
  default     = "Kore"
}

variable "answer_audio_retention_days" {
  description = "How long a recorded interview answer stays in the bucket before the lifecycle rule deletes it (ADR 0013)."
  type        = number
  default     = 30
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name. Used in the WIF attribute condition."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the budget alert attaches to. Find with: gcloud billing accounts list"
  type        = string
  sensitive   = true
}

variable "budget_amount" {
  description = "Monthly spend that triggers the budget alert, in the billing account's currency."
  type        = number
  default     = 50
}

variable "budget_currency" {
  description = "Must match the billing account's currency (gcloud billing accounts describe <id> → currencyCode); the Budgets API rejects any other with a bare 400."
  type        = string
  default     = "SGD"
}

variable "ingest_max_attempts" {
  description = "Deliveries Cloud Tasks makes of one ingest job before giving up (ADR 0034). Also given to the worker, which fails the job on the last one."
  type        = number
  default     = 5
}

variable "api_max_instances" {
  description = "Hard cap on Cloud Run instances. Keeps both cost and (later) Cloud SQL connection count bounded. 1 for Phase 0."
  type        = number
  default     = 1
}

variable "app_domain" {
  description = "Custom domain for the frontend, served by Firebase Hosting (ADR 0008)."
  type        = string
  default     = "anyview.anyapps.cloud"
}

variable "cors_origins" {
  description = "Browser origins allowed to call the API (ADR 0006): the custom domain plus the two default Hosting origins."
  type        = list(string)
  default = [
    "https://anyview.anyapps.cloud",
    "https://anyapps-anyview.web.app",
    "https://anyapps-anyview.firebaseapp.com",
  ]
}

variable "allowed_emails" {
  description = "Google account emails allowed past sign-in (ADR 0009). [\"*\"] lets in any verified Google account (ADR 0041). Empty means nobody can start an interview."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "alert_emails" {
  description = "Emails that get a notification on every sign-up (ADR 0042). Empty creates no alert."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "local_signers" {
  description = "IAM members allowed to sign upload URLs as the API service account from a laptop, e.g. [\"user:you@example.com\"]. roles/owner does not include signBlob. Empty in CI/production."
  type        = list(string)
  default     = []
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-g1-small per the brief (~USD 25-30/month idle); db-f1-micro is the step-down if the budget bites."
  type        = string
  default     = "db-g1-small"
}

variable "db_owner_iam_user" {
  description = "Google account that may log in to the database with IAM auth from a laptop (migrations, tests, break-glass). Usually the project owner."
  type        = string
  sensitive   = true # an email; kept out of the plan CI posts on a PR
}

variable "db_password_version" {
  description = "Bump to rotate the built-in postgres user's password (ADR 0011). The value itself is never in state."
  type        = number
  default     = 1
}
