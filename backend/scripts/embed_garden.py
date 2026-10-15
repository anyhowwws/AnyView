"""Embed every garden entry that has no current vector (ADR 0038). Run once after
the deploy that adds embeddings, and again after `EMBED_RENDER_VERSION` changes.

    cd backend && GOOGLE_CLOUD_PROJECT=anyapps-anyview DB_INSTANCE=<project:region:instance> \\
        DB_IAM_USER=<you> .venv/bin/python scripts/embed_garden.py

Uses the app's own wiring (`main.build_model`, `main.build_repository`): your
ADC for Vertex and for the Cloud SQL connector, never a key. Or point it at a
local database with DATABASE_URL. Safe to run again: an entry whose vector is
current is skipped, so a second run embeds nothing.

The same writes heal a garden on their own (every garden write embeds whatever
is stale), so this only saves waiting for the next write.
"""

from __future__ import annotations

import sys

from anyview.api.brain import embedder
from anyview.main import build_model, build_repository


def main() -> int:
    repo = build_repository()
    model = build_model()
    total = 0
    for uid in repo.user_ids():
        count = repo.embed_garden(uid, embedder(model))
        total += count
        print(f"{uid}: {count} embedded")
    print(f"done: {total} entries embedded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
