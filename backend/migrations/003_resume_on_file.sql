-- 003: the resume becomes a property of the user (ADR 0014), and re-ingesting
-- one stops repeating itself (ADR 0015).
--
-- Additive only, as every migration here is. Nothing drops, nothing changes a
-- constraint: `raw_dumps` keeps its original CHECK on `kind`, and a job
-- description never becomes a dump at all — it is read, shown to the user and
-- carried in the session, not remembered.

-- Which dump holds the resume an interviewer would receive. A pointer, not
-- "the most recent resume dump wins": adding a second CV to the garden as raw
-- material must not silently change what interviewers see.
ALTER TABLE users ADD COLUMN resume_dump_id uuid REFERENCES raw_dumps (id);

-- The hash of the *extracted text*, not the file bytes: the same CV exported
-- twice from Word differs byte for byte and extracts identically, and that is
-- the case worth catching (ADR 0015).
ALTER TABLE raw_dumps ADD COLUMN text_sha256 char(64);
CREATE INDEX raw_dumps_user_hash_idx ON raw_dumps (user_id, text_sha256);

-- Backfill: hex sha256 of the UTF-8 text, which is what Python's
-- hashlib.sha256(text.encode()).hexdigest() produces for the same string.
UPDATE raw_dumps SET text_sha256 = encode(sha256(convert_to(text, 'UTF8')), 'hex');

-- Existing users keep the resume they last uploaded, so nobody is asked to
-- re-upload a CV the garden already holds.
UPDATE users u
   SET resume_dump_id = (
     SELECT d.id FROM raw_dumps d
      WHERE d.user_id = u.uid AND d.kind IN ('resume_pdf', 'resume_docx')
      ORDER BY d.created_at DESC
      LIMIT 1
   );
