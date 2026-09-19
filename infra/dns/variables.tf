variable "app_domain" {
  description = "Custom domain for the frontend, served by Firebase Hosting (ADR 0008). Must match the main stack's var.app_domain."
  type        = string
  default     = "anyview.anyapps.cloud"
}

variable "dns_zone_name" {
  description = "Route 53 hosted zone that holds app_domain's records."
  type        = string
  default     = "anyapps.cloud"
}

variable "hosting_site_id" {
  description = "The Firebase Hosting site the domain should resolve to. Must match the main stack's var.project_id — the default site id is the project id, and this record is written statically rather than read back from the Firebase resource (see main.tf)."
  type        = string
  default     = "anyapps-anyview"
}
