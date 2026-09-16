"""Shared fixtures. A realistic Setup so prompt and engine tests read naturally."""

import pytest

from anyview.interview.models import Setup

RESUME = """Jordan Lee — Cloud Solutions Architect

Acme Corp (2021–present) — Senior Cloud Architect
- Led migration of the billing service from VMs to Cloud Run, cutting monthly infra cost 38%.
- Designed the Terraform module library now used by 6 product teams.
- Ran the on-call rota redesign after two Sev-1 incidents; MTTR dropped from 4h to 50m.

Globex (2018–2021) — DevOps Engineer
- Built the CI/CD pipeline for 40 microservices on GitHub Actions.
- Introduced cost dashboards that surfaced $120k/yr of idle resources.
"""


@pytest.fixture
def setup() -> Setup:
    return Setup(
        resume=RESUME,
        company="Initech",
        role="Cloud Architect",
        seniority="senior",
        job_description="Own the platform roadmap. Strong communication with product teams.",
    )
