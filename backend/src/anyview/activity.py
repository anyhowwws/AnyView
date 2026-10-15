"""Product activity, one JSON log line per thing a person did (ADR 0042).

Cloud Run turns a log line that is a JSON object into a structured entry
(`jsonPayload`), and Terraform's log-based metrics (`infra/monitoring.tf`)
count the entries by `jsonPayload.activity`. So adding a counter is two
steps: call `record("<name>")` here, add the name to the metric list there.

No email, uid or free text goes in a line: the metrics count, they do not
identify anyone, and logs are kept longer than an erased account (ADR 0018).
"""

from __future__ import annotations

import json
import logging

activity_log = logging.getLogger("anyview.activity")

# The names the dashboard knows. A name outside this set is a typo; failing a
# test is better than a counter that silently stays at zero.
ACTIVITIES = frozenset(
    {
        "signup",  # first request from a new account (a users row was created)
        "interview_started",  # an interview was planned
        "interview_completed",  # its report was scored
        "discover_question",  # a question asked of Donna
        "garden_upload",  # a resume or text queued for extraction
    }
)


def record(activity: str) -> None:
    if activity not in ACTIVITIES:
        raise ValueError(f"unknown activity {activity!r}")
    activity_log.info(json.dumps({"activity": activity}))
