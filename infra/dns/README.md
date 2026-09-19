# infra/dns

The one AWS resource in this repository: the Route 53 CNAME that points
`anyview.anyapps.cloud` at Firebase Hosting.

Split out from the main GCP stack by ADR 0012 so that stack never needs AWS
credentials to plan or apply — every routine change (Cloud Run, Cloud SQL,
IAM, etc.) is now `aws login`-free. This stack is applied rarely, only when
the domain itself changes, and only from a laptop with `aws login` — never
from CI.

## Commands

```sh
cd infra/dns
terraform init
terraform plan
terraform apply
```

State lives in the same GCS bucket as the main stack, under a different
prefix (`anyview/dns`), so `terraform init` needs no `-backend-config` flag —
the bucket name is fixed in `providers.tf`.
