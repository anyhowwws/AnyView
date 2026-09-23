-- 005: erasing a whole account (ADR 0018).
--
-- The event log stays append-only: history is never rewritten. The one
-- exception is erasing an account, which deletes a user's entire stream at
-- once. `Repository.erase_user` marks that intent for its own transaction with
--
--     SELECT set_config('anyview.erasing_user', <uid>, true)
--
-- (`true` = transaction-local: it cannot leak into a pooled connection's next
-- transaction). Only a DELETE of that user's rows passes; an UPDATE never does,
-- and neither does a DELETE of anyone else's events in the same transaction.
--
-- Replacing the function keeps the trigger that calls it: no schema change.

CREATE OR REPLACE FUNCTION events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE'
     AND OLD.user_id = current_setting('anyview.erasing_user', true) THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'events is append-only: % on event % refused', TG_OP, OLD.id
    USING ERRCODE = 'integrity_constraint_violation';
END $$;
