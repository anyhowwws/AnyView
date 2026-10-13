-- 008: target jobs are remembered (ADR 0025, reversing one line of ADR 0014).
--
-- A plain table, outside the event log: a saved job is a choice about the
-- practice setup, not a fact about the candidate, so it needs no provenance and
-- no replay. Editing one is an UPDATE; deleting one is a DELETE.
--
-- `source` says which path filled it in, because the two are edited
-- differently: an uploaded posting's text is the posting and stays read-only,
-- while a filled-in job's text is rebuilt from `fields` every time it changes.
CREATE TABLE saved_jobs (
  id              uuid PRIMARY KEY,
  user_id         text NOT NULL REFERENCES users (uid),
  company         text NOT NULL,
  role            text NOT NULL,
  seniority       text NOT NULL,
  source          text NOT NULL CHECK (source IN ('upload', 'manual')),
  -- What the prompt carries as `job_description`. NULL when only the company,
  -- role and seniority were given.
  job_description text,
  -- The form's structured fields (team, responsibilities, must-haves,
  -- nice-to-haves), one item per line, exactly as the form holds them.
  fields          jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Hash of the uploaded posting's text: the same file read twice is the same
  -- job, and a re-upload skips the parse call (ADR 0015's idea, applied here).
  text_sha256     char(64),
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_used_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX saved_jobs_user_idx ON saved_jobs (user_id, last_used_at DESC);
CREATE INDEX saved_jobs_user_hash_idx ON saved_jobs (user_id, text_sha256);
