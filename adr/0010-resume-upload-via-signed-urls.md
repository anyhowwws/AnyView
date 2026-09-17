# 0010 — Resume upload: signed URLs into Cloud Storage, PDF read by the model

- **Status:** Accepted
- **Date:** 2026-09-18

## Context

Phase 0 took the resume as pasted plain text. Real resumes are PDFs and Word
files, and a pasted abstract loses the structure the interviewer needs. The
brief already specifies the mechanism ("PDF and DOCX upload via signed URL;
PDF read by the model natively, DOCX converted to text first") as part of
Phase 2 ingestion; this pulls it forward, before the brain exists, because
the interview is unusable without it.

Two constraints shaped the design: the file must never transit the API (brief),
and everything downstream — prompt caching, quoting `cited_resume_lines`, the
50–15,000 character limits — works on text.

## Options considered

**Multipart upload through the API.** Simplest to build. Puts a 10 MB body
through Cloud Run on every upload and makes the API the file's custodian;
ruled out by the brief.

**Signed URL, browser to bucket.** The API issues a short-lived V4 signed PUT
URL for an object it names; the browser uploads directly; the API reads the
object back later. The bucket needs a CORS rule for the app's origins.

**PDF text: extract locally or let the model read it.** A PDF's text layer is
unreliable (columns, headers, ligatures, none at all when scanned). The model
has to understand the document anyway, so one cheap transcription call
produces clean text, and the rest of the pipeline is unchanged. DOCX has a
real structure, so `python-docx` reads it with no model call.

**Signing.** Cloud Run credentials carry no private key, and neither does a
developer's ADC. The storage library can sign through the IAM `signBlob` API
as a named service account; the API's own SA holds `serviceAccountTokenCreator`
on itself, and the owner has it locally. No key file is created anywhere.

## Decision

- `POST /uploads` validates type (PDF, DOCX) and size (≤ 10 MB), names the
  object `uploads/<uid>/<uuid>.<ext>` — the browser's filename never appears —
  and returns a 15-minute signed PUT URL.
- `POST /interview/start` accepts `resume_object` instead of `resume` text
  (exactly one). It refuses objects outside the caller's own prefix, reads the
  bytes, extracts text (DOCX → `python-docx`; PDF → one model call with the
  file inline, `call="extract"`), and from there it is the Phase 0 pipeline.
- `Setup.resume_object` records the source. It is the object Phase 2's
  `RawDump` will point at; nothing expires the bucket.
- Pasting text stays as a secondary path in the UI (and as the test/fake path).

## What this costs

- **Two dependencies** in the backend, each doing one thing:
  `google-cloud-storage` (signed URLs, reading objects) and `python-docx`.
- **One extra model call per PDF** (Pro at low effort, ~2k tokens, ~10 s).
  Cheap next to the interview it starts; DOCX pays nothing.
- **A bucket with CORS** and one more IAM edge (the SA signing as itself).
  Both scoped to the one bucket and the one SA.
- **The upload is not virus-scanned or content-checked** beyond type and size.
  Only allow-listed users can upload, and only the model and `python-docx`
  ever open the bytes. Revisit if uploads are ever opened by anything else.
- **Extraction is repeated per interview** for the same object. Phase 2's
  review queue stores the extracted entities once; until then a re-upload or
  a second interview on the same file re-extracts.
