"""Runtime configuration, read once from environment variables.

Cloud Run injects these from Terraform (`infra/cloud_run.tf`); locally they come
from your shell or a git-ignored `.env`. Plain `os.environ` on purpose — a
settings library would be a dependency for six fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    project_id: str
    vertex_region: str
    model_id: str
    fast_model_id: str
    cors_origins: list[str] = field(default_factory=list)
    use_fake_model: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        # `frozen=True` makes the instance immutable, so it is safe to share
        # across requests. A missing GOOGLE_CLOUD_PROJECT is allowed here so
        # tests and the fake model can run without any GCP context; the real
        # adapter refuses to start without it.
        origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
        return cls(
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            vertex_region=os.environ.get("VERTEX_REGION", "global"),
            model_id=os.environ.get("MODEL_ID", "gemini-3.1-pro-preview"),
            fast_model_id=os.environ.get("MODEL_ID_FAST", "gemini-3.8-flash"),
            cors_origins=origins or ["http://localhost:3000"],
            use_fake_model=os.environ.get("ANYVIEW_FAKE_MODEL", "0") == "1",
        )
