-- 009: ingestion runs as a queued job, not inside the request (ADR 0034).
--
-- A plain table, outside the event log, like saved_jobs: a job is the
-- machinery that produces a proposal, not a fact about the candidate. What it
-- produces (the raw dump, the proposal) is recorded where it always was.
--
-- The browser polls a row by id; the worker that Cloud Tasks calls claims it,
-- reports progress into it, and finishes it. Every column the browser needs to
-- show where Donna is lives here, so a reload or a new API instance loses
-- nothing.
CREATE TABLE ingest_jobs (
  id            uuid PRIMARY KEY,
  user_id       text NOT NULL REFERENCES users (uid),
  -- What was handed in: typed text, or an uploaded file's object name.
  source        text NOT NULL CHECK (source IN ('text', 'upload')),
  input_text    text,
  object_name   text,
  status        text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed')),
  -- The `progress` frames so far, in order, exactly as the stream used to send
  -- them. A new attempt starts the list again.
  progress      jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- Deliveries that got as far as claiming the job.
  attempts      int NOT NULL DEFAULT 0,
  -- Set once the text is read, so a retry does not read (or transcribe) it again.
  raw_dump_id   uuid REFERENCES raw_dumps (id),
  proposal_id   uuid REFERENCES proposals (id),
  -- A failure the browser shows, and the HTTP status the old route would have sent.
  error         text,
  error_status  int,
  created_at    timestamptz NOT NULL DEFAULT now(),
  -- Bumped by every claim and every progress frame: the worker's heartbeat. A
  -- running job whose heartbeat is old belongs to a delivery that died.
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK ((source = 'text') = (input_text IS NOT NULL)),
  CHECK ((source = 'upload') = (object_name IS NOT NULL))
);
CREATE INDEX ingest_jobs_user_idx ON ingest_jobs (user_id, created_at DESC);
