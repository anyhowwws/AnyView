# 0041 — Sign-in opens to any verified Google account

- **Status:** Accepted, amended by 0047 (a daily limit per user)
- **Date:** 2026-10-16
- **Amends:** 0009 (who is allowed in)

## Context

ADR 0009 allow-listed sign-in by email because every session spends the
owner's model budget. The app is going live, and the allow-list now blocks the
people it is going live for. Someone off the list could already sign in to
Google and see the screens; every API call then answered 403 ("isn't on the
access list"), which reads as a broken app.

## Decision

`ALLOWED_EMAILS` accepts `*`, meaning any Google account with a verified email.
An empty list still lets nobody in, so a missing variable fails closed. The
gate itself is unchanged: every route still requires a valid Firebase ID token
for this project, and the browser shows only the sign-in card until there is
one.

Production sets the GitHub secret `TF_ALLOWED_EMAILS` to `["*"]` (a secret
rather than a variable since ADR 0042). Going back to a list is the same
secret, followed by a run of the pipeline on main; no code changes.

The privacy page and the sign-in card no longer say access is by invitation;
the sign-in card says nothing about who may sign in, so it is right either way.

## Consequences

- Anyone with a Google account can run interviews on the owner's budget. The
  budget alert (`infra/budget.tf`) only alerts; it does not stop spending.
- Usage is counted (ADR 0042), and a new sign-up emails the owner.
- Usage is already recorded per user (`users`, `usage_events`), which is what
  any later per-user limit would read.
