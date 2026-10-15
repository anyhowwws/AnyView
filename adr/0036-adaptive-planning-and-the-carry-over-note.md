# 0036 — Adaptive planning between questions, and the carry-over note

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amends:** 0031 (what Harvey reads on Live), 0028 (the plan is no longer fixed once made)

## Context

The interview is planned once, at the start: five questions, one competency each (ADR 0016).
After that the plan cannot react. If the candidate's answer to question 2 already covers what
question 3 asks, they are asked to repeat themselves. If they open a thread that fits a later
competency better, nothing picks it up.

Each spoken question is its own Live session (ADR 0031), so Harvey remembers earlier answers only
through excerpts of them in his instruction: 600 characters of each one, and 1,200 of the last.
Follow-ups are not included, and the excerpts grow with every question.

The owner also considered running one loop for the whole interview. ADR 0031 already rejected
one Live session per interview because its cost grows with the square of the turn count, it has
a ten-minute connection cap, and Harvey drifts further from the plan with every question. It
also moves control of the plan from the server to the model, which is the opposite of what
guardrails need. One loop per question already has a natural point between questions where the
server is back in control, and that is where this decision acts.

## Decision

**One planner call between questions.** `POST /interview/answer` records the answer as before
(`engine.submit_answer`, still pure). When another question follows, `engine.adapt` makes one
structured call (`call="adapt"`, fast model, effort `low`) that does two jobs:

1. **It rewrites the carry-over note** (`Session.notes`): at most six short lines of what the
   candidate actually said (projects, numbers, decisions, open threads), built from the full
   transcript, follow-ups included. It contains no judgements and no scores. At Panel it may
   cite garden labels.
2. **It may reword the next question.** It does so only when an earlier answer already covered
   it, or opened a thread that fits its competency better. Keeping the question is the usual
   outcome.

**The server sets the limits, not the model:**

- Only the next question can change, and only its `text` and `rationale`. Its id, `competency`
  and `seconds` stay as planned, so the plan still covers every competency.
- The number of questions is fixed (`QUESTION_COUNT`), and so are the follow-ups (`MAX_PROBES`).
- The wording planned at the start is kept on `Question.planned`. A second rewrite keeps the
  first plan, not the first rewrite.
- The text is capped (`MAX_QUESTION_CHARS` = 400, `MAX_NOTES_CHARS` = 1,200) and trimmed, not
  refused.
- The planner reads `session_system(setup)`, the same system text as the plan, so it knows
  exactly what the interviewer knows: the garden only at Panel. That text is also a cache hit.
- **It is best effort.** A model failure, a refusal, a malformed reply, an empty question, or no
  reply within `ADAPT_DEADLINE_S` (6 s) leaves the session as it was, and the planned question
  is asked. An answer of `(no answer given)` with no follow-ups makes no call at all.

**Harvey reads the note.** On Live, `live_system` puts the note in place of the older excerpts
and keeps only the last answer's excerpt, which the bridge needs (ADR 0032). With no note (the
planner failed, or this is question 1), it falls back to the excerpts as before. The note is
built only from what the candidate said in this interview, so it adds nothing the interviewer
should not know, and it is used at every difficulty.

The turn-based fallback and typed answers get the reworded question too (`ask` reads
`question.text`), but not the note: `ask` is a fixed lead-in with no model call (ADR 0028).

## Consequences

- One more fast-model call per question after the first: four per interview, about one to
  three seconds each, between a question's end and the next one opening. Each writes a usage row.
- Harvey can refer back ("earlier you mentioned…") to anything in the note, not just the excerpts.
  His instruction stops growing with every question.
- The report scores the question that was actually asked. The planned wording stays on the
  session for later use; the report does not show it yet.
- The browser still carries the session (Phase 0), so it carries the note too. A tampered note
  only affects the user's own practice session, the same as a tampered question already did.
- **Not done here:** retrieval as a tool. At Panel the whole garden is still in Harvey's
  instruction, and `ask_follow_up` still answers only `allowed` / `follow_ups_left`.

## Alternatives rejected

- **One loop for the whole interview.** See Context and ADR 0031.
- **Letting the planner change the question count or the competency.** It would make the
  interview length, the report and the cost unpredictable, and coverage would depend on the model.
- **The judgement model (3.1 Pro) for the planner.** It thinks for 4–6 s before its first token,
  and this call sits between two spoken questions.
- **Running the planner while the next question opens.** The reworded question has to be in the
  Live instruction before Harvey speaks, so the call cannot overlap the opening of the next question.
