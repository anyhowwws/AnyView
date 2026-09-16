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
  description = "Region the Claude model is served from on Vertex AI. May differ from var.region."
  type        = string
  default     = "us-east5"
}

variable "claude_model" {
  description = "Vertex AI model ID the API calls. A variable so a model change is a plan, not a code change."
  type        = string
  default     = "claude-sonnet-4-5@20250929"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name. Used in the WIF attribute condition."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the budget alert attaches to. Find with: gcloud billing accounts list"
  type        = string
}

variable "budget_amount_usd" {
  description = "Monthly spend that triggers the budget alert."
  type        = number
  default     = 50
}

variable "api_max_instances" {
  description = "Hard cap on Cloud Run instances. Keeps both cost and Cloud SQL connection count bounded."
  type        = number
  default     = 2
}
