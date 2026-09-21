"""Turn an uploaded resume or architecture diagram into usable source text.

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
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
# The upload ticket is shared by the resume flow and the Digital Garden. The
# interview route still accepts only PDFs and DOCX files as a resume source.
ALLOWED_TYPES = {PDF: ".pdf", DOCX: ".docx", PNG: ".png", JPEG: ".jpg", WEBP: ".webp"}
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


DIAGRAM_SYSTEM = """You read architecture diagrams for a job seeker's Digital Garden.
Return a faithful plain-text inventory of only what is visibly labelled or directly represented:
systems, components, data flows, cloud services, technologies, responsibilities, and measurable
outcomes. Preserve labels where possible. State no guesses, no implied technologies, no commentary,
and no Markdown table."""


def diagram_to_text(data: bytes, mime_type: str, *, model: Model, session_id: str) -> str:
    reply = model.generate(
        system=DIAGRAM_SYSTEM,
        user="Read the attached architecture diagram and return its factual contents.",
        session_id=session_id,
        call="extract",
        effort="low",
        max_tokens=4096,
        attachment=(data, mime_type),
    )
    if reply.refused or not reply.text.strip():
        raise ExtractionError(
            "That architecture diagram could not be read. Try a clearer PNG, JPG, or WebP."
        )
    if reply.truncated:
        raise ExtractionError(
            "That architecture diagram has too much detail to read in one go. Try a focused crop."
        )
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
