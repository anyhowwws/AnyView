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
    tts_model_id: str = "gemini-2.5-flash-preview-tts"
    harvey_voice: str = "Charon"
    donna_voice: str = "Kore"
    # Harvey on Gemini Live (ADR 0031). Live models are regional, not `global`.
    live_model_id: str = "gemini-3.8-live"
    live_region: str = "us-central1"
    cors_origins: list[str] = field(default_factory=list)
    allowed_emails: frozenset[str] = frozenset()
    upload_bucket: str = ""
    db_instance: str = ""  # project:region:instance; empty = no database
    db_name: str = "anyview"
    db_iam_user: str = ""
    database_url: str = ""  # local/test override: a plain postgres:// URL
    signer_service_account: str = ""
    # Queued ingestion (ADR 0034). An empty queue runs jobs in this process.
    tasks_queue: str = ""  # projects/<p>/locations/<r>/queues/<name>
    worker_url: str = ""  # the private worker service Cloud Tasks calls
    tasks_invoker: str = ""  # the service account Cloud Tasks signs its token as
    ingest_max_attempts: int = 5  # the queue's max_attempts; the worker's last try fails the job
    use_fake_model: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        # `frozen=True` makes the instance immutable, so it is safe to share
        # across requests. A missing GOOGLE_CLOUD_PROJECT is allowed here so
        # tests and the fake model can run without any GCP context; the real
        # adapter refuses to start without it.
        origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
        # Lower-cased so the comparison in api/auth.py is case-insensitive. An
        # empty list means nobody gets in, which is the safe default.
        emails = frozenset(
            e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()
        )
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        return cls(
            project_id=project,
            vertex_region=os.environ.get("VERTEX_REGION", "global"),
            model_id=os.environ.get("MODEL_ID", "gemini-3.1-pro-preview"),
            fast_model_id=os.environ.get("MODEL_ID_FAST", "gemini-3.5-flash-lite"),
            # Voice mode (ADR 0013). A TTS model is a different model family, so
            # it gets its own id; the voice is one of Vertex's prebuilt speakers.
            tts_model_id=os.environ.get("TTS_MODEL_ID", "gemini-2.5-flash-preview-tts"),
            harvey_voice=os.environ.get("HARVEY_VOICE", "Charon"),
            # Donna speaks only in Discover's speak mode (ADR 0030).
            donna_voice=os.environ.get("DONNA_VOICE", "Kore"),
            live_model_id=os.environ.get("LIVE_MODEL_ID", "gemini-3.8-live"),
            live_region=os.environ.get("LIVE_REGION", "us-central1"),
            cors_origins=origins or ["http://localhost:3000"],
            allowed_emails=emails,
            upload_bucket=os.environ.get("UPLOAD_BUCKET", ""),
            db_instance=os.environ.get("DB_INSTANCE", ""),
            db_name=os.environ.get("DB_NAME", "anyview"),
            db_iam_user=os.environ.get("DB_IAM_USER", ""),
            database_url=os.environ.get("DATABASE_URL", ""),
            # Signed URLs are signed by the API's own service account via the IAM
            # signBlob API; locally your ADC calls it on the SA's behalf.
            signer_service_account=os.environ.get(
                "SIGNER_SERVICE_ACCOUNT", f"anyview-api@{project}.iam.gserviceaccount.com"
            ),
            tasks_queue=os.environ.get("TASKS_QUEUE", ""),
            worker_url=os.environ.get("WORKER_URL", ""),
            tasks_invoker=os.environ.get("TASKS_INVOKER", ""),
            # Set from the same Terraform variable as the queue's retry_config.
            ingest_max_attempts=int(os.environ.get("INGEST_MAX_ATTEMPTS", "5")),
            use_fake_model=os.environ.get("ANYVIEW_FAKE_MODEL", "0") == "1",
        )
