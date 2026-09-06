"""Tests for micro-intervention suggestions."""
from app import interventions


def test_stable_tier_returns_maintain():
    out = interventions.suggest(0, [])
    assert len(out) == 1
    assert out[0]["key"] == "maintain"


def test_elevated_tier_targets_top_signals():
    top = [
        {"key": "sleep_hours", "label": "Sleep"},
        {"key": "social_count", "label": "Social contact"},
    ]
    out = interventions.suggest(2, top, max_items=2)
    assert len(out) == 2
    keys = {o["key"] for o in out}
    assert "sleep_hours" in keys
    assert "social_count" in keys
    for o in out:
        assert o["action"] and o["title"] and o["rationale"] and o["duration"]


def test_unknown_signal_falls_back():
    out = interventions.suggest(1, [{"key": "nonexistent", "label": "X"}])
    assert len(out) >= 1  # always offers something at an elevated tier


def test_interventions_in_status_after_seed(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    s = client.get("/api/status").json()
    assert "interventions" in s
    assert len(s["interventions"]) >= 1
    # A declining demo ends elevated, so it should be an actionable suggestion,
    # not the 'maintain' affirmation.
    assert s["interventions"][0]["key"] != "maintain"
