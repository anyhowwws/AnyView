# Usage monitoring (ADR 0042): how many people signed up, how many interviews
# ran, how many questions Donna answered. No new service and no new dependency:
# the app writes one JSON log line per thing a person did (anyview/activity.py)
# and one per model call (the `anyview.usage` line, llm/adapter.py). Cloud Run
# stores a JSON line as a structured entry, and the log-based metrics below
# count those entries. The dashboard reads the metrics.
#
# A log-based metric counts from the moment it exists; it does not backfill.
# Earlier history is in the database (`users`, `usage_events`).

locals {
  # Both services built from the API image log these lines; the worker logs
  # the model calls of a resume upload.
  app_logs = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name=("${google_cloud_run_v2_service.api.name}" OR "${google_cloud_run_v2_service.worker.name}")
  EOT

  # Every name in anyview/activity.py:ACTIVITIES, with its tile title. A test
  # (tests/test_activity.py) fails if one is missing here.
  activities = {
    "signup"              = "Sign-ups"
    "interview_started"   = "Interviews started"
    "interview_completed" = "Interviews completed (report scored)"
    "discover_question"   = "Questions asked of Donna"
    "garden_upload"       = "Garden uploads"
  }

  activity_metric = "logging.googleapis.com/user/${google_logging_metric.activity.name}"
  model_metric    = "logging.googleapis.com/user/${google_logging_metric.model_calls.name}"
}

# One counter, labelled by activity, rather than one metric per activity: a new
# activity needs a tile, not a new metric.
resource "google_logging_metric" "activity" {
  name        = "anyview_activity"
  description = "Things people did in AnyView, one per anyview.activity log line (ADR 0042)."
  filter      = "${local.app_logs} jsonPayload.activity:*"

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "AnyView activity"
    labels {
      key         = "activity"
      value_type  = "STRING"
      description = "signup, interview_started, interview_completed, discover_question, garden_upload"
    }
  }

  label_extractors = {
    activity = "EXTRACT(jsonPayload.activity)"
  }

  depends_on = [google_project_service.enabled]
}

# Every model call, by what it was for (`call`: plan, score, discover, live, …)
# and which model answered. Where the budget goes, on a chart.
resource "google_logging_metric" "model_calls" {
  name        = "anyview_model_calls"
  description = "Model calls, one per anyview.usage log line (ADR 0042)."
  filter      = "${local.app_logs} jsonPayload.call:* jsonPayload.model:*"

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "AnyView model calls"
    labels {
      key        = "call"
      value_type = "STRING"
    }
    labels {
      key        = "model"
      value_type = "STRING"
    }
  }

  label_extractors = {
    call  = "EXTRACT(jsonPayload.call)"
    model = "EXTRACT(jsonPayload.model)"
  }

  depends_on = [google_project_service.enabled]
}

resource "google_monitoring_dashboard" "usage" {
  # The dashboard is JSON in the Monitoring API's own schema. Built with
  # jsonencode so the per-activity tiles come from the map above.
  dashboard_json = jsonencode({
    displayName = "AnyView usage"
    mosaicLayout = {
      columns = 12
      tiles = concat(
        # Row 1: one number per activity, the total over the last 7 days.
        [for i, name in keys(local.activities) : {
          xPos   = (i % 4) * 3
          yPos   = floor(i / 4) * 4
          width  = 3
          height = 4
          widget = {
            title = "${local.activities[name]} (7 days)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"${local.activity_metric}\" resource.type=\"cloud_run_revision\" metric.label.activity=\"${name}\""
                  aggregation = {
                    alignmentPeriod    = "604800s"
                    perSeriesAligner   = "ALIGN_SUM"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        }],
        [
          {
            xPos   = 0
            yPos   = 8
            width  = 12
            height = 5
            widget = {
              title = "Activity per day"
              xyChart = {
                dataSets = [{
                  plotType = "STACKED_BAR"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.activity_metric}\" resource.type=\"cloud_run_revision\""
                      aggregation = {
                        alignmentPeriod    = "86400s"
                        perSeriesAligner   = "ALIGN_SUM"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.activity"]
                      }
                    }
                  }
                }]
              }
            }
          },
          {
            xPos   = 0
            yPos   = 13
            width  = 12
            height = 5
            widget = {
              title = "Model calls per day, by call"
              xyChart = {
                dataSets = [{
                  plotType = "STACKED_BAR"
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"${local.model_metric}\" resource.type=\"cloud_run_revision\""
                      aggregation = {
                        alignmentPeriod    = "86400s"
                        perSeriesAligner   = "ALIGN_SUM"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.call"]
                      }
                    }
                  }
                }]
              }
            }
          },
        ],
      )
    }
  })

  depends_on = [google_project_service.enabled]
}
