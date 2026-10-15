-- 010: one embedding per confirmed project, story, achievement and feedback (ADR 0003, 0038).
--
-- Derived, like the projection, and outside the event log: it can always be
-- recomputed from the entities. No foreign key to the entity tables, on
-- purpose: `rebuild` deletes and replays a user's projection with the same ids,
-- and a cascade would throw every vector away with it. Search joins to the live
-- entities instead, so a retired entity's row is simply never returned.
--
-- `text_sha256` is the hash of the text that was embedded. A write compares it
-- with the entity's text now: a different hash, or no row, means the entity
-- needs embedding. `render_version` is the version of that rendering
-- (`repository.EMBED_RENDER_VERSION`); changing how an entity renders to text
-- changes every hash, so every entity is re-embedded on its next write.
--
-- No vector index yet: one user's garden is tens to hundreds of rows, and an
-- exact scan of those is faster than maintaining an index.
CREATE TABLE entity_embeddings (
  entity_id      uuid PRIMARY KEY,
  user_id        text NOT NULL REFERENCES users (uid),
  kind           text NOT NULL CHECK (kind IN ('project', 'story', 'achievement', 'feedback')),
  embedding      vector(768) NOT NULL,
  text_sha256    text NOT NULL,
  render_version int NOT NULL,
  model          text NOT NULL,
  embedded_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX entity_embeddings_user_kind_idx ON entity_embeddings (user_id, kind);
