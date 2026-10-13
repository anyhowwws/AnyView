# 0029 — Harvey interviews; Donna keeps the Digital Garden

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0013, 0016, 0026, 0028 (wherever they name Donna as the interviewer)

## Context

One persona, Donna, did two different jobs: she asked the practice interview's questions out
loud, and she answered questions about the confirmed Digital Garden. Those are different rooms.
One is a performance under a clock with a voice. The other is a read-only conversation over the
candidate's own record, with no voice yet. Giving them one name also made copy awkward: "Donna
read your resume", "Donna moves on when the clock runs out", "Ask Donna about your garden".

## Decision

- **Harvey is the interviewer.** Practice, the pre-flight, the fixed lead-ins and interjections,
  the speaker check, the pace blurb and every error shown during an interview use his name.
  Copy avoids pronouns for him; "Harvey" or "the interviewer" instead.
- **Donna is the Digital Garden's assistant.** Discover, the review queue, resume and dump
  extraction, and the capture box keep her name. Her voice is not decided yet.
- **Harvey's voice is configured as `HARVEY_VOICE`**, default **`Orus`**.
  `DONNA_VOICE` and the Terraform variable `donna_voice` are gone, along with the frontend's
  `DonnaVoice`/`donnaVoice()`. The garden gets its own setting when she gets a voice.
- **The voice name was checked against Vertex, not assumed.** "Orbit" was the first choice, but
  a synthesis call with it returns `400 INVALID_ARGUMENT`; `Orus` and `Charon` both succeed.
  An unknown voice name fails every spoken question, and the app then falls back to text, so a
  wrong name would have looked like "voice is broken". Orus was chosen as the nearest name.

## Consequences

- Earlier ADRs (0013, 0016, 0026, 0028) still say "Donna" for the interviewer. They stay as
  written: ADRs are records of what was decided then.
- **Terraform must be applied** to set `HARVEY_VOICE` on the Cloud Run service. Until then the
  API uses the in-code default (`Orus`), so nothing breaks, but `terraform.tfvars` containing
  `donna_voice` will warn about an undeclared variable and should be updated.
- A saved interview session in a browser carries no persona text, so nothing to migrate.
- When Donna gets a voice, her setting, the prompt for it and a decision about the shared
  `/interview/say` route belong in a new ADR.
