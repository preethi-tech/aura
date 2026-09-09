"""Tests for the personalized intervention-effectiveness loop (Feature 3)."""
from app import interventions


def _hist():
    return [
        {"intervention_key": "social_count", "delta": -8.0},
        {"intervention_key": "social_count", "delta": -6.0},
        {"intervention_key": "energy", "delta": 1.0},
        {"intervention_key": "sleep_hours", "delta": -5.0},
        {"intervention_key": "sleep_hours", "delta": -3.0},
    ]


def test_effectiveness_aggregation():
    eff = interventions.effectiveness(_hist())
    assert eff["social_count"]["n"] == 2
    assert eff["social_count"]["avg_delta"] == -7.0
    assert eff["energy"]["avg_delta"] == 1.0


def test_best_proven_picks_biggest_drop():
    bp = interventions.best_proven(_hist())
    assert bp is not None
    assert bp["key"] == "social_count"      # -7 avg beats sleep's -4
    assert bp["proven"] is True


def test_best_proven_requires_evidence():
    assert interventions.best_proven([]) is None
    assert interventions.best_proven(
        [{"intervention_key": "energy", "delta": 2.0}]) is None


def test_suggest_annotates_and_reranks():
    top = [
        {"key": "sleep_hours", "label": "Sleep"},
        {"key": "social_count", "label": "Social contact"},
    ]
    out = interventions.suggest(2, top, history=_hist())
    # social_count is 'proven' and most effective -> should be first.
    assert out[0]["key"] == "social_count"
    assert out[0].get("proven") is True
    assert "effect_text" in out[0]


# --- API loop ---------------------------------------------------------------
def test_try_and_resolve_loop(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    # Try an intervention now -> logs index_before, pending resolution.
    t = client.post("/api/interventions/try", json={"key": "social_count"}).json()
    assert t["logged"] is True
    assert t["index_before"] is not None
    # Next check-in resolves it (index_after measured).
    client.post("/api/entries", json={
        "journal_text": "went for a walk and texted a friend, felt better",
        "sleep_hours": 7, "social_count": 3, "energy": 4,
    })
    # History now contains resolved deltas -> status carries a proven pick.
    s = client.get("/api/status").json()
    assert "proven_intervention" in s


def test_seeded_history_populates_proven(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    s = client.get("/api/status").json()
    # Seeded intervention history should yield a proven-for-you suggestion.
    assert s["proven_intervention"] is not None
    assert s["proven_intervention"]["proven"] is True
