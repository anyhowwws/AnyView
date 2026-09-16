# State lives in the bucket created by ./bootstrap. The bucket name is supplied
# at init time so no project-specific value is committed here:
#
#   terraform init -backend-config="bucket=<project>-tfstate"
#
# GCS backend locks natively; no separate lock resource needed.
terraform {
  backend "gcs" {
    prefix = "anyview/main"
  }
}
