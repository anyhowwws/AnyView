"""A daily cap per user on the two expensive things (ADR 0047).

Sign-in is open to any verified Google account (ADR 0041), and each interview
or garden upload makes several Pro calls. Ten of each per user per UTC day is
plenty for practice and bounds what one account can spend.

Usage, as a `with` block around the work:

    with daily(repo, user, "interview"):
        ...plan the interview...

The slot is taken on entry (429 if none is left) and given back if the block
raises, so a failed attempt does not use up the day. Without a database
(`repo is None`, a laptop run) there is nothing to count against, and no limit.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException

from anyview.api.auth import CurrentUser

DAILY_LIMIT = 10

_SPENT = {
    "interview": f"You've started {DAILY_LIMIT} interviews today, the daily limit. "
    "It resets at midnight UTC.",
    "upload": f"You've added {DAILY_LIMIT} uploads or notes for Donna to read today, the daily "
    "limit. It resets at midnight UTC. Entries you type in a form don't count.",
}


@contextmanager
def daily(repo: Any, user: CurrentUser, action: str) -> Iterator[None]:
    if repo is None:
        yield
        return
    repo.ensure_user(user.uid, user.email)  # the counter row points at the user's row
    if not repo.take_daily(user.uid, action, DAILY_LIMIT):
        raise HTTPException(429, _SPENT[action])
    try:
        yield
    except BaseException:
        repo.give_back_daily(user.uid, action)
        raise
