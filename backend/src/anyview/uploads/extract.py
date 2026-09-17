"""Turn an uploaded resume into the plain text the interview pipeline uses.

Two file types, two routes (ADR 0010):
  - DOCX: `python-docx` reads paragraphs and table cells. No model call.
  - PDF:  the model reads the file natively and returns a faithful plain-text
          rendering. A PDF's text layer is unreliable (columns, headers,
          ligatures, or none at all when scanned), and the model already has to
          understand the document; asking it to transcribe first is one cheap
          call that makes everything downstream — caching, quoting resume
          lines — work on clean text.

Both return text that then passes the same `Setup.resume` limits as pasted
text, so nothing after this point knows where the resume came from.
"""

from __future__ import annotations

import io

from docx import Document

from anyview.llm.adapter import Model

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_TYPES = {PDF: ".pdf", DOCX: ".docx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SIGNED_URL_TTL_SECONDS = 15 * 60


class ExtractionError(Exception):
    """The file could not be turned into usable text. `user_message` is safe to show."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def docx_to_text(data: bytes) -> str:
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises a few types for bad zips/xml
        raise ExtractionError("That .docx file could not be opened.") from exc

    lines: list[str] = [p.text for p in doc.paragraphs]
    # Resumes often keep dates and roles in tables; walk them in reading order.
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            lines.append(" | ".join(c for c in cells if c))
    text = "\n".join(line.rstrip() for line in lines)
    return _tidy(text)


PDF_SYSTEM = (
    "You transcribe resumes. Return the document's text as plain text in reading "
    "order: headings, roles with employer and dates, bullet points as lines starting "
    "with '- ', contact details as given. Keep every fact and number; add nothing; "
    "do not summarise, comment, or format as Markdown tables."
)


def pdf_to_text(data: bytes, *, model: Model, session_id: str) -> str:
    reply = model.generate(
        system=PDF_SYSTEM,
        user="Transcribe the attached resume.",
        session_id=session_id,
        call="extract",
        effort="low",
        max_tokens=8192,
        attachment=(data, PDF),
    )
    if reply.refused or not reply.text.strip():
        raise ExtractionError(
            "The PDF could not be read. Try exporting it again, or paste the text."
        )
    if reply.truncated:
        raise ExtractionError("That PDF is too long to read in one go. Please shorten it.")
    return _tidy(reply.text)


def _tidy(text: str) -> str:
    # Collapse runs of blank lines; keep single blanks as section breaks.
    out: list[str] = []
    blank = False
    for line in text.splitlines():
        if line.strip():
            out.append(line.rstrip())
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()
