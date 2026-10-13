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
- **Harvey's voice is configured as `HARVEY_VOICE`**, default **`Charon`** (chosen by ear after auditioning; first `Orus`, then `Alnilam`, which read as British in a real run).
  `DONNA_VOICE` and the Terraform variable `donna_voice` are gone, along with the frontend's
  `DonnaVoice`/`donnaVoice()`. The garden gets its own setting when she gets a voice.
- **The voice name was checked against Vertex, not assumed.** "Orbit" was the first choice, but
  a synthesis call with it returns `400 INVALID_ARGUMENT`; `Orus` and `Charon` both succeed.
  An unknown voice name fails every spoken question, and the app then falls back to text, so a
  wrong name would have looked like "voice is broken". Orus was the first stand-in, until Alnilam was picked.

- **Harvey has a delivery.** `prompts.HARVEY_DELIVERY` is direction for the TTS model, put in
  front of every line he speaks as `"<style>: <line>"` (`adapter.spoken_prompt`): a smooth
  baritone with a strong Brooklyn New York accent and a faint smirk, brisk and clipped, dry
  and slightly smug. It is a code constant, not an environment variable: it is part of who
  Harvey is, and changing it is a reviewed change.
- **What auditioning taught us, so it need not be learned twice.**
  - A long direction that asked for "deliberate pauses" ran ~30% slower than plain speech
    (9.6 s against 7.2 s for a sample question): drop pause and relaxed-pace wording.
  - Alnilam with a "New York closer" direction still sounded British to the owner. A direction
    that only names a persona does not fix an accent: name the accent, and prefer a voice
    that does not fight it.
  - A separate accent line with negations ("never British, never mid-Atlantic") made the model
    **read the instructions aloud**: seven-second lines became 41–54 s. Keep accent and
    pace in one short, positive clause (the shipped one measured 6.7 s on Charon).
  - **Length is the safety check:** a clip far longer than the line alone means the direction
    is being spoken. Transcribing it confirms. An automated accent rating by a model is not
    reliable (it judges the words, and rated the British-sounding clip "0/10 British"): accent
    is checked by ear.
  - One styled "let's move on" once came back with its line said twice; three repeats were
    normal, so no guard is added. Mind the TTS quota (requests per minute per model) when
    auditioning: generate clips slowly.

## Consequences

- Earlier ADRs (0013, 0016, 0026, 0028) still say "Donna" for the interviewer. They stay as
  written: ADRs are records of what was decided then.
- **Terraform must be applied** to set `HARVEY_VOICE` on the Cloud Run service. Until then the
  API uses the in-code default (`Orus`), so nothing breaks, but `terraform.tfvars` containing
  `donna_voice` will warn about an undeclared variable and should be updated.
- A saved interview session in a browser carries no persona text, so nothing to migrate.
- When Donna gets a voice, her setting, the prompt for it and a decision about the shared
  `/interview/say` route belong in a new ADR.
