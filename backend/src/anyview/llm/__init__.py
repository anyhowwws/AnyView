"""Model access. Application code imports `Model`, `Reply`, `ModelError` from
here and never touches the `google.genai` package directly (ADR 0004, 0007)."""

from anyview.llm.adapter import Model, ModelError, Reply, Usage

__all__ = ["Model", "ModelError", "Reply", "Usage"]
