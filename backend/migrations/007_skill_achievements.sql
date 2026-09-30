-- 007: a certification can evidence a skill (ADR 0020).
--
-- Shaped like skill_evidence and skill_roles: the link lives on the skill
-- side, and both ends cascade, so erasing a user (ADR 0018) and rebuilding a
-- projection clear it with its parents. Events written before this migration
-- carry no achievement links and replay unchanged.
CREATE TABLE skill_achievements (
  skill_id       uuid NOT NULL REFERENCES skills (id) ON DELETE CASCADE,
  achievement_id uuid NOT NULL REFERENCES achievements (id) ON DELETE CASCADE,
  PRIMARY KEY (skill_id, achievement_id)
);
