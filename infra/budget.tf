# Day-one budget alert. Notifications go to the billing account's admins by
# default; a Pub/Sub topic can be wired in later if programmatic action is wanted.
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "AnyView monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  depends_on = [google_project_service.enabled]
}

data "google_project" "this" {
  project_id = var.project_id
}
