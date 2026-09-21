-- 002: Digital Garden expands the confirmed profile with resume-native sections.
-- Certifications remain achievements with kind = 'credential'; education and
-- languages need distinct, editable projections and retain event provenance.

CREATE TABLE education (
  id            uuid PRIMARY KEY,
  user_id       text NOT NULL REFERENCES users (uid),
  institution   text NOT NULL,
  qualification text,
  field         text,
  start_date    date,
  end_date      date,
  raw_dump_id   uuid NOT NULL REFERENCES raw_dumps (id),
  event_id      bigint NOT NULL REFERENCES events (id),
  retired_at    timestamptz
);
CREATE INDEX education_user_idx ON education (user_id);

CREATE TABLE languages (
  id          uuid PRIMARY KEY,
  user_id     text NOT NULL REFERENCES users (uid),
  name        text NOT NULL,
  proficiency text,
  raw_dump_id uuid NOT NULL REFERENCES raw_dumps (id),
  event_id    bigint NOT NULL REFERENCES events (id),
  retired_at  timestamptz
);
CREATE UNIQUE INDEX languages_live_name_idx ON languages (user_id, lower(name)) WHERE retired_at IS NULL;
