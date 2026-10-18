-- 011: a daily cap per user on the two expensive things (ADR 0047).
--
-- Sign-in is open to any Google account (ADR 0041), and an interview or a
-- garden upload costs several Pro calls. One row per user, UTC day and action,
-- counted up by `Repository.take_daily` in a single statement, so two requests
-- at once can never both take the last slot.
--
-- A plain counter, outside the event log: it is not a fact about the
-- candidate. Erasing an account deletes it with everything else.
CREATE TABLE daily_usage (
  user_id  text NOT NULL REFERENCES users (uid),
  day      date NOT NULL,
  action   text NOT NULL CHECK (action IN ('interview', 'upload')),
  count    int  NOT NULL CHECK (count >= 0),
  PRIMARY KEY (user_id, day, action)
);
