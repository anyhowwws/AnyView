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
  description = "Vertex AI location the model is served from. \"global\" is recommended for current-generation models; may differ from var.region."
  type        = string
  default     = "global"
}

variable "model_id" {
  description = "Vertex AI model for judgement calls: plan, score, ideal (ADR 0007). A variable so a model change is a plan, not a code change."
  type        = string
  default     = "gemini-3.1-pro-preview"
}

variable "fast_model_id" {
  description = "Vertex AI model for streamed interviewer turns, where time-to-first-token matters more than depth."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name. Used in the WIF attribute condition."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the budget alert attaches to. Find with: gcloud billing accounts list"
  type        = string
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

variable "api_max_instances" {
  description = "Hard cap on Cloud Run instances. Keeps both cost and (later) Cloud SQL connection count bounded. 1 for Phase 0."
  type        = number
  default     = 1
}
