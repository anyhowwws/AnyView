# This stack manages exactly one thing: the Route 53 DNS record that points
# the app's custom domain at Firebase Hosting (ADR 0008, split out by
# ADR 0012 so the main GCP stack no longer needs AWS credentials to apply).
#
# Credentials come from the local `aws login` session. This stack is applied
# from a laptop, never from CI — there is no AWS identity in GitHub.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    bucket = "anyapps-anyview-tfstate"
    prefix = "anyview/dns"
  }
}

provider "aws" {
  region = "us-east-1" # Route 53 is a global service; the region only satisfies the provider
}
