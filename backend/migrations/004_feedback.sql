-- 004: Feedback joins the Digital Garden as its own entity kind — a quote or
-- close paraphrase of what someone else said about the candidate's work,
-- optionally tied to the role or project it concerns. Additive only, like
-- every migration here.

CREATE TABLE feedback (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  role_id     uuid REFERENCES roles (id),
  project_id  uuid REFERENCES projects (id),
  given_by    text NOT NULL,           -- who said it, or where it came from
  content     text NOT NULL,           -- the feedback itself, verbatim or close
  received_on date,
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE INDEX feedback_user_idx ON feedback (user_id);
