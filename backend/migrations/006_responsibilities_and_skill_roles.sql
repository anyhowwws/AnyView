-- 006: roles carry what the candidate did continuously in them, and skills can
-- be evidenced by a role as well as by a project (ADR 0019).
--
-- Additive only. Events written before this migration have neither field; the
-- projection reads a missing field as empty, so replaying them is unchanged.

-- Short statements of ongoing work ("EKS day-2 operations", "RFQ and pre-sales
-- support"). Bounded work with an outcome is a project, not a responsibility.
ALTER TABLE roles ADD COLUMN responsibilities text[] NOT NULL DEFAULT '{}';

-- Shaped like skill_evidence: a skill used in a role's ongoing work, where no
-- single project is the honest answer. Both sides cascade, so erasing a user
-- (ADR 0018) and rebuilding a projection clear it with its parents.
CREATE TABLE skill_roles (
  skill_id uuid NOT NULL REFERENCES skills (id) ON DELETE CASCADE,
  role_id  uuid NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
  PRIMARY KEY (skill_id, role_id)
);
