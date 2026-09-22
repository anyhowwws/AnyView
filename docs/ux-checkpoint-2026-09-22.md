# Digital Garden UX audit and checkpoint

## Summary
The graph is the signature experience: a bird’s-eye view of confirmed career
knowledge. The surrounding web UI should use the same dark teal material with
quiet controls. This is a web audit using HIG foundations, not native Apple
navigation conventions. Evidence: user screenshot and frontend source review.
Authenticated end-to-end and visual checks remain outstanding.

## Implemented
- Critical: graph outline button inherited a light page background under light
  text. Shared role-based palette now covers page, card, popover, forms and actions.
  `dark-mode.md › Dark Mode colors`: “Aim for sufficient color contrast in all
  appearances.” Automated checks enforce 4.5:1 for principal text pairs and 3:1
  for input boundaries/focus. Native controls and scrollbars use dark appearance.
- High: hard-coded pale capture, upload, section-header and view-switch surfaces
  replaced by shared tokens (Law of Similarity).
- High: /brain did not mark Digital Garden active. Both Garden URLs now identify
  the current page (Jakob’s Law).
- Medium: larger graph labels, 44px legend targets and explicit Clear selection
  action. `buttons.md › Best practices`: “Make buttons easy for people to use.”
  Fitts’s Law informs target sizes; full titles remain in the entry inspector.
- High: coverage now doubles color with visible symbols and a legend; role headers
  wrap rather than truncate. `accessibility.md › Vision`: “Convey information
  with more than color alone.”
- Medium: sign-in copy now introduces the Garden before interview practice
  (Serial Position Effect). Existing review-before-confirm, inline errors,
  retirement confirmation and progressive disclosure are retained.

## Design system
Dark page #08191f; raised card #0d2227; text #e1eeeb; secondary text #adc4bf;
mint action #83dfcc with dark text; error #ffaaa5. Existing Geist retained: one
font, 32–48px page titles, 24px feature heading, 14–16px body/control text.
No extra decorative animations or dependencies. Dark-only is the owner's explicit
direction; it intentionally differs from HIG’s default system-appearance guidance.

Desktop: header → capture → review → graph | inspector.
Compact: header/nav → capture → review → graph → inspector.
Two top-level destinations and three grouped Garden views remain unchanged
(Hick’s Law); templates keep fields local rather than requiring cross-screen
memory (Miller’s Law). No workflow steps added.

## Follow-up / not yet verified
- Authenticated desktop/mobile checks: selected graph, native and portalled
  selects, formatted capture, proposal review, editing, interview and report.
- Keyboard and 200% text zoom walkthrough; verify increased-contrast mode on
  actual devices. The CSS supports larger touch targets and reduced motion.
- Automated browser-level accessibility and interaction coverage is still not
  present; current tests cover graph layout and color-token contrast only.

## Completed after the audit
- Dense graph labels now use a deterministic, connection-first collision pass.
  The selected entry’s label always remains visible; the inspector and entry
  finder retain full titles.
- Garden load failures now present an in-place retry action rather than leaving
  a dead-end error.
- Interview submissions now preserve a typed or transcribed answer if the API
  call fails. The draft clears only after a successful response.

This checkpoint separates shipped presentation fixes from remaining flow work;
do not describe the whole application as fully accessibility-verified.
