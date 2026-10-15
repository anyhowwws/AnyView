# 0041 — Sign-in opens to any verified Google account

- **Status:** Accepted
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

Production sets the GitHub variable `TF_ALLOWED_EMAILS` to `["*"]`. Going back
to a list is the same variable.

## Consequences

- Anyone with a Google account can run interviews on the owner's budget. The
  budget alert (`infra/budget.tf`) only alerts; it does not stop spending.
- Usage is already recorded per user (`users`, `usage_events`), which is what
  any later per-user limit would read.
