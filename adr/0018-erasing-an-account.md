# 0018 — Erasing an account: the one delete the event log allows

- **Status:** Accepted
- **Date:** 2026-09-24
- **Amends:** 0011 (the append-only event log)

## Context

AnyView stores personal career data: resumes (the file and its full text),
everything a user captures, recorded interview answers. Until now nothing
could actually be deleted. **Retire** hides an entry in the projection, and
the event that retired it joins the log. The raw dumps, including the resume
text, stay. If a user wanted their data gone, for privacy or any other
reason, the only answer was a person running SQL by hand.

That is not acceptable for an app that asks people to hand over their CV. A
user must be able to erase everything themselves.

The obstacle is deliberate. ADR 0011 made the event log append-only in the
database: a trigger refuses every `UPDATE` and `DELETE` on `events`, so
history cannot be rewritten by a bug.

## Options considered

**Drop the trigger, or let the app role bypass it.** Erasure becomes easy,
and so does every accidental rewrite the trigger exists to stop.

**Crypto-shredding.** Encrypt each user's payloads with their own key (KMS)
and delete the key to erase. The log stays untouched. This is the textbook
event-sourcing answer, but it means encrypting every column that holds
content, a KMS key per user, and decrypting on every read. Far too much for
a single-instance app with a few users.

**Mark the erasure inside the transaction.** The trigger allows a `DELETE`
only when the same transaction has first named the user being erased, and
only for that user's rows. `UPDATE` stays refused, always.

## Decision

**Mark the erasure inside the transaction.**

- Migration `005_erasure.sql` replaces the trigger function. A `DELETE` passes
  when `OLD.user_id = current_setting('anyview.erasing_user', true)`. Every
  other delete, and every update, raises as before.
- `Repository.erase_user(uid)` is the only code that sets that value. It uses
  `set_config(..., true)`, which lasts for this transaction only, so a pooled
  connection cannot carry it into its next transaction. It then deletes every
  table's rows for the user, children before parents (`ERASE_ORDER`), in one
  transaction. A test fails if a table with a `user_id` column is missing from
  that list.
- `POST /account/erase` deletes the user's Cloud Storage objects first
  (`uploads/<uid>/` and `audio/<uid>/`), then the rows. If the bucket fails,
  nothing has been deleted yet and a retry is clean. The other order could
  leave files behind with no account left to find them from. Erasing is safe
  to repeat.
- The body must carry the phrase the user typed (`"delete my data"`), so a
  stray or scripted call erases nothing.
- The browser then deletes the user's Identity Platform sign-in record with
  Firebase's `deleteUser`. Firebase only allows that from a recently
  signed-in client. When the sign-in is too old, the browser signs out
  instead and says so. That record holds only the email and uid, not any of
  the user's data. The API gets no Identity Platform admin rights just for
  this.
- The only record of an erasure is a log line with the uid and row and file
  counts. It holds no content and no email.

The rule ADR 0011 enforces becomes: **history is never rewritten; a whole
account can be erased.**

## What this costs

- **Backups keep the data for up to 7 days** (`retained_backups = 7`, no
  point-in-time recovery). The erase page says so rather than promising
  instant, total deletion.
- **The guard stops accidents, not a hostile app.** The API role owns the
  schema (ADR 0011), so it could always have dropped the trigger. That was
  already true. What the guard does is keep ordinary code from deleting
  events by mistake.
- **`ERASE_ORDER` is a list to maintain.** A new table holding user data has to
  join it. The test makes that a CI failure rather than a silent leak.
- **Startup migrations now include one that changes behaviour**, not just
  schema. It is a `CREATE OR REPLACE FUNCTION`, safe to re-run and backwards
  compatible, and the API owns the function (checked in production before
  merging).
- **Usage rows written without a uid are not erased.** Most usage lines are
  keyed only by session id and hold token counts, no content. They cannot be
  tied back to a person, so there is nothing personal to erase.
