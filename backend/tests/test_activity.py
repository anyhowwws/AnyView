"""Activity lines (ADR 0042): what the dashboard counts."""

import json
import logging

import pytest

from anyview.activity import ACTIVITIES, record


def test_a_line_is_a_json_object_with_only_the_name(caplog):
    with caplog.at_level(logging.INFO, logger="anyview.activity"):
        record("signup")
    assert [json.loads(r.getMessage()) for r in caplog.records] == [{"activity": "signup"}]


def test_an_unknown_name_is_refused():
    with pytest.raises(ValueError):
        record("sign_up")


def test_every_name_has_a_metric():
    """Each activity needs a log-based metric in infra/monitoring.tf, or it is never counted."""
    from pathlib import Path

    tf = (Path(__file__).parents[2] / "infra" / "monitoring.tf").read_text()
    for name in ACTIVITIES:
        assert f'"{name}"' in tf, name
