"""Turn an uploaded resume or spoken answer into text.

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

A third route, added by voice mode (ADR 0013): a recorded answer goes to the
same model as audio and comes back as the words that were said. Nothing
downstream can tell a spoken answer from a typed one.
"""

from __future__ import annotations

import io

from docx import Document

from anyview.llm.adapter import Model

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# The upload ticket is shared by the resume flow and the Digital Garden; both
# take the same two document types.
ALLOWED_TYPES = {PDF: ".pdf", DOCX: ".docx"}

# Spoken answers (ADR 0013). What the browser can actually record depends on
# the browser: Chrome and Firefox produce WebM/Opus, Safari produces MP4/AAC.
WEBM = "audio/webm"
MP4A = "audio/mp4"
OGG = "audio/ogg"
AUDIO_TYPES = {WEBM: ".webm", MP4A: ".m4a", OGG: ".ogg"}
EXTENSION_TYPES = {ext: mime for mime, ext in AUDIO_TYPES.items()}

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
    "with '- ', contact details as given. Keep each section's content together under "
    "its heading: when the page has columns, finish one column's section before "
    "starting the next, and never interleave lines from two columns. Write headings "
    "as ordinary words, even when the page letter-spaces them. Keep list separators "
    "(commas, '·') as written. Keep every fact and number; add nothing; do not "
    "summarise, comment, or format as Markdown tables."
)


def pdf_to_text(data: bytes, *, model: Model, session_id: str) -> str:
    # The fast model: transcribing is copying, not judging, and on the judgement
    # model it was 20 s of every upload (ADR 0019). The recall script checks
    # that nothing is lost.
    reply = model.generate(
        system=PDF_SYSTEM,
        user="Transcribe the attached resume.",
        session_id=session_id,
        call="extract",
        effort="low",
        max_tokens=8192,
        attachment=(data, PDF),
        fast=True,
    )
    if reply.refused or not reply.text.strip():
        raise ExtractionError(
            "The PDF could not be read. Try exporting it again, or paste the text."
        )
    if reply.truncated:
        raise ExtractionError("That PDF is too long to read in one go. Please shorten it.")
    return _tidy(reply.text)


ANSWER_SYSTEM = (
    "You transcribe spoken interview answers. Return exactly what the speaker said, as "
    "plain prose with ordinary punctuation and paragraph breaks where they pause. Keep "
    "every fact, name, and number as spoken. Remove only stammers and filler words "
    "('um', 'uh', 'you know'). Do not summarise, correct, rephrase, translate, or add "
    "commentary. If the recording contains no speech, return nothing at all."
)


def audio_to_text(data: bytes, mime_type: str, *, model: Model, session_id: str) -> str:
    """A recorded answer, transcribed. The model reads audio the same way it
    reads a PDF — as an attachment — so this needs no speech API (ADR 0013)."""
    reply = model.generate(
        system=ANSWER_SYSTEM,
        user="Transcribe the attached recording of the candidate's answer.",
        session_id=session_id,
        call="transcribe",
        effort="low",
        max_tokens=4096,
        attachment=(data, mime_type),
    )
    if reply.refused:
        raise ExtractionError("That recording could not be transcribed. Please try again.")
    text = _tidy(reply.text)
    if not text:
        raise ExtractionError("We didn't catch any speech in that recording. Try again.")
    if reply.truncated:
        raise ExtractionError("That answer was too long to transcribe. Keep it under four minutes.")
    return text


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
