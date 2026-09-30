# 0020 — Certifications evidence skills

Status: Accepted
Date: 2026-09-30

## Context

ADR 0019 made skills link to the roles and projects that show them, each link
with a checked quote. Certifications still linked to nothing: in the graph
they float free, and the interviewer cannot tell that "Security Specialty"
stands behind a claimed skill in threat detection. A credential is evidence
of a different kind from a project. It says an exam was passed, not that the
work was done. It is still evidence, and it is often the only kind a resume
gives for a platform.

## Decision

**Credentials become a third target of the linking pass (ADR 0019).**

- `skill_achievements (skill_id, achievement_id)`, migration `007`, shaped like
  `skill_evidence` and `skill_roles`. The link lives on the skill:
  `Skill.achievement_ids`, `SkillDraft.achievements`.
- Only `kind = "credential"` achievements are targets. An award evidences
  nothing about a skill.
- The model may link a certification to a skill when its name names the skill,
  the platform the skill is ("AWS" for any AWS certification), or the skill's
  own subject ("Advanced Networking" for hybrid cloud networking). Sharing a
  vendor is not enough.
- **A credential's stretch is its own evidence quote.** Certifications sit in
  lists, and one list line is valid evidence for every credential on it
  (ADR 0019). So "the quote is inside the target's text" cannot tell them
  apart. The code adds a second check: the quote must share a distinctive word
  with the credential's own title, after dropping words every certification
  shares ("AWS", "Certified", "Associate", "Specialty"…). A title's adjacent
  word pairs also count as their initials, so "SA Associate" names "Solutions
  Architect – Associate".

## Consequences

- The graph draws credential → skill edges, and certifications stop floating
  free when a resume gives them a subject. `brain_context` says "certified by
  A3" beside a skill, so the interviewer and Discover can tell a certified
  claim from a practised one.
- The word check is conservative. A credential whose name shares no word with
  the quote is dropped rather than guessed, and the user can still add the link
  by hand.
- Linking a certification to a skill that was confirmed from an earlier dump
  works the same way roles and projects do (ADR 0019): the skill draft is
  adopted as an update, and the links it already had are kept.

## Alternatives rejected

- **Links on the achievement (`achievement.skill_ids`).** It puts the same kind
  of relationship on two sides. Every other "what evidences this skill" link is
  on the skill, and the queue shows them in one place.
- **A vendor rule in code (every AWS certification evidences every AWS
  skill).** It is cheap, and wrong: a Cloud Practitioner does not evidence
  Amazon EKS.
