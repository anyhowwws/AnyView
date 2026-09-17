-- 001: the second brain (ADR 0002, 0011).
--
-- Invariants the database enforces, not the code:
--   * provenance: every projection row points at the raw dump it came from and
--     the event that wrote it (NOT NULL foreign keys)
--   * the event log is append-only (trigger)
--   * one live skill per name per user (partial unique index)
--   * competencies come from the fixed taxonomy (CHECK)

CREATE EXTENSION IF NOT EXISTS vector;  -- created by db_bootstrap.py on Cloud SQL; no-op here

CREATE TABLE users (
  uid        text PRIMARY KEY,           -- Firebase uid
  email      text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- The unedited original of everything the user gave us.
CREATE TABLE raw_dumps (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  kind        text NOT NULL CHECK (kind IN ('text', 'resume_pdf', 'resume_docx')),
  text        text NOT NULL,             -- typed text, or the extracted text of a file
  object_name text,                      -- Cloud Storage object, files only
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX raw_dumps_user_idx ON raw_dumps (user_id, created_at DESC);

-- The review queue: what the model proposed from one dump.
CREATE TABLE proposals (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending', 'confirmed', 'discarded')),
  patch       jsonb NOT NULL,            -- the model's proposal, untouched
  model       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX proposals_user_status_idx ON proposals (user_id, status);

-- The source of truth. Every change to the brain is one row here.
CREATE TABLE events (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  seq         integer NOT NULL,          -- per-user order; replay follows it
  kind        text NOT NULL CHECK (kind IN ('patch_confirmed', 'entity_edited', 'entity_retired')),
  payload     jsonb NOT NULL,
  raw_dump_id uuid REFERENCES raw_dumps (id),
  proposal_id uuid REFERENCES proposals (id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, seq)
);

CREATE FUNCTION events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'events is append-only: % on event % refused', TG_OP, OLD.id
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER events_append_only
  BEFORE UPDATE OR DELETE ON events
  FOR EACH ROW EXECUTE FUNCTION events_append_only();

-- ---------------------------------------------------------------------------
-- Projection: the current brain, rebuildable from events at any time.
-- ---------------------------------------------------------------------------

CREATE TABLE roles (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  company     text NOT NULL,
  title       text NOT NULL,
  start_date  date,
  end_date    date,                      -- NULL = current
  level       text,
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE INDEX roles_user_idx ON roles (user_id);

CREATE TABLE projects (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  role_id     uuid REFERENCES roles (id), -- NULL for side projects
  name        text NOT NULL,
  problem     text,
  action      text,
  result      text,
  tech        text[] NOT NULL DEFAULT '{}',
  metrics     text[] NOT NULL DEFAULT '{}',
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE INDEX projects_user_idx ON projects (user_id);

-- The fixed competency taxonomy. Changing it is a migration, on purpose.
CREATE TABLE competencies (
  key   text PRIMARY KEY,
  label text NOT NULL,
  ord   smallint NOT NULL
);
INSERT INTO competencies (key, label, ord) VALUES
  ('ownership',       'Ownership',        1),
  ('ambiguity',       'Ambiguity',        2),
  ('conflict',        'Conflict',         3),
  ('failure',         'Failure',          4),
  ('influence',       'Influence',        5),
  ('leadership',      'Leadership',       6),
  ('collaboration',   'Collaboration',    7),
  ('communication',   'Communication',    8),
  ('customer_focus',  'Customer focus',   9),
  ('technical_depth', 'Technical depth', 10),
  ('delivery',        'Delivery',        11);

CREATE FUNCTION competencies_known(keys text[]) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT keys <@ (SELECT coalesce(array_agg(key), '{}') FROM competencies)
$$;

CREATE TABLE stories (
  id           uuid PRIMARY KEY,
  user_id      text NOT NULL REFERENCES users (uid),
  role_id      uuid REFERENCES roles (id),
  project_id   uuid REFERENCES projects (id),
  title        text NOT NULL,
  situation    text,
  task         text,
  action       text,
  result       text,
  competencies text[] NOT NULL DEFAULT '{}' CHECK (competencies_known(competencies)),
  raw_dump_id  uuid NOT NULL REFERENCES raw_dumps (id),
  event_id     bigint NOT NULL REFERENCES events (id),
  retired_at   timestamptz
);
CREATE INDEX stories_user_idx ON stories (user_id);
CREATE INDEX stories_competencies_idx ON stories USING gin (competencies);

CREATE TABLE skills (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  name        text NOT NULL,
  depth       smallint NOT NULL CHECK (depth BETWEEN 1 AND 5),  -- self-rated
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE UNIQUE INDEX skills_live_name_idx ON skills (user_id, lower(name)) WHERE retired_at IS NULL;

CREATE TABLE skill_evidence (
  skill_id   uuid NOT NULL REFERENCES skills (id) ON DELETE CASCADE,
  project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  PRIMARY KEY (skill_id, project_id)
);

CREATE TABLE achievements (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  kind        text NOT NULL CHECK (kind IN ('achievement', 'credential')),
  title       text NOT NULL,
  issuer      text,
  achieved_on date,
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE INDEX achievements_user_idx ON achievements (user_id);

-- One row per model call (the Phase 0 log line, now queryable).
CREATE TABLE usage_events (
  id              bigserial PRIMARY KEY,
  user_id         text REFERENCES users (uid),
  session_id      text NOT NULL,
  call            text NOT NULL,
  model           text NOT NULL,
  input_tokens    integer NOT NULL,
  output_tokens   integer NOT NULL,
  thinking_tokens integer NOT NULL,
  cache_read      integer NOT NULL,
  latency_ms      integer NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_events_session_idx ON usage_events (session_id);
CREATE INDEX usage_events_created_idx ON usage_events (created_at);
