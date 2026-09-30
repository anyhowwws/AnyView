"""How much does extraction find in one document? A manual recall check (ADR 0019).

    cd backend && GOOGLE_CLOUD_PROJECT=anyapps-anyview \\
        .venv/bin/python scripts/extraction_recall.py ~/Downloads/resume.pdf \\
        --expect achievements=14 education=2 languages=2 roles=2

Runs the real pipeline against Vertex (your ADC, never a key): transcribe if
it is a PDF or DOCX, then `propose()` against an empty garden. Prints what
came out per kind, which drafts were flagged unverified, every skill link with
its quote, and what each model call cost. With `--expect`, exits non-zero when
a kind comes back short, so a prompt change can be checked against a document
whose right answer you know.

Tests never call Google (CLAUDE.md), so this is a script, not a test. It
writes nothing: no database, no bucket. Keep the documents you run it on out
of the repository: a real resume is personal data.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

from anyview.brain.extract import propose
from anyview.config import Settings
from anyview.llm import adapter
from anyview.llm.adapter import VertexGemini
from anyview.uploads.extract import docx_to_text, pdf_to_text

KINDS = (
    "roles", "projects", "stories", "skills", "achievements", "education", "languages", "feedback",
)  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("document", type=Path, help="a .pdf, .docx or .txt file")
    parser.add_argument(
        "--expect", nargs="*", default=[], metavar="KIND=N", help="minimum count per kind"
    )
    args = parser.parse_args()
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        sys.exit("set GOOGLE_CLOUD_PROJECT")

    settings = Settings.from_env()
    model = VertexGemini(
        project_id=settings.project_id,
        region=settings.vertex_region,
        model=settings.model_id,
        fast_model=settings.fast_model_id,
    )
    calls: list[dict] = []
    adapter.usage_sink = calls.append  # every call's usage row, collected instead of stored

    session = f"recall-{uuid.uuid4().hex[:8]}"
    data = args.document.read_bytes()
    suffix = args.document.suffix.lower()
    if suffix == ".pdf":
        text = pdf_to_text(data, model=model, session_id=session)
    elif suffix == ".docx":
        text = docx_to_text(data)
    else:
        text = data.decode("utf-8")

    patch = propose(text, brain_index="", model=model, session_id=session)

    print(f"\n{len(text):,} characters of text\n")
    for kind in KINDS:
        drafts = getattr(patch, kind)
        flagged = sum(d.unverified for d in drafts)
        print(f"{kind:13} {len(drafts):3}" + (f"   ({flagged} unverified)" if flagged else ""))
    print("\nSkill links:")
    for skill in patch.skills:
        for target in (*skill.projects, *skill.roles):
            quote = skill.link_evidence.get(target, "(label from an earlier dump)")
            print(f"  {skill.name} → {target}: {quote!r}")
    print("\nModel calls:")
    for call, n in Counter(c["call"] for c in calls).items():
        tokens = sum(c["output_tokens"] for c in calls if c["call"] == call)
        print(f"  {call:10} ×{n}   {tokens:,} output tokens (incl. thinking)")

    short = []
    for item in args.expect:
        kind, _, want = item.partition("=")
        got = len(getattr(patch, kind))
        if got < int(want):
            short.append(f"{kind}: {got} < {want}")
    if short:
        print("\nShort:", "; ".join(short))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
