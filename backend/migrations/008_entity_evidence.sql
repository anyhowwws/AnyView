-- 008: each entry keeps the quote that justified it (ADR 0023).
--
-- Additive: a nullable column per entity table. Events confirmed before this
-- carry no quote and replay with NULL; the card then shows where the entry
-- came from without a quote. An entry added by hand keeps its form text here,
-- which the card does not repeat (the entry *is* that text).
ALTER TABLE roles        ADD COLUMN evidence text;
ALTER TABLE projects     ADD COLUMN evidence text;
ALTER TABLE stories      ADD COLUMN evidence text;
ALTER TABLE skills       ADD COLUMN evidence text;
ALTER TABLE achievements ADD COLUMN evidence text;
ALTER TABLE education    ADD COLUMN evidence text;
ALTER TABLE languages    ADD COLUMN evidence text;
ALTER TABLE feedback     ADD COLUMN evidence text;
