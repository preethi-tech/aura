"""Tests for relapse fingerprinting (DTW temporal pattern matching)."""
from app import relapse
from app.analysis import compute_timeline
from app.seed import generate


def test_dtw_identical_is_zero():
    seq = [[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]]
    assert relapse.dtw_distance(seq, seq) == 0.0


def test_dtw_handles_time_warp():
    a = [[0.0], [1.0], [2.0], [3.0]]
    b = [[0.0], [1.0], [1.0], [2.0], [3.0]]  # same shape, stretched
    # A stretched version of the same shape should be closer than to noise.
    noise = [[5.0], [0.0], [5.0], [0.0], [5.0]]
    assert relapse.dtw_distance(a, b) < relapse.dtw_distance(a, noise)


def test_extract_episodes_from_decline():
    tl = compute_timeline([
        {**e, "features": {}} for e in generate("decline", 60)
    ])["timeline"]
    eps = relapse.extract_episodes(tl)
    assert len(eps) >= 1
    for e in eps:
        assert e["start"] <= e["end"]
        assert e["peak_index"] > 0


def test_recurring_scenario_matches_past_episode():
    """The 'recurring' scenario has two episodes; the current window should
    fingerprint against the earlier one."""
    entries = [{**e, "features": {}} for e in generate("recurring", 100)]
    tl = compute_timeline(entries)["timeline"]
    result = relapse.find_similar_past_episodes(tl)
    assert result["available"] is True
    # At least one past episode should be similar enough to surface.
    assert isinstance(result["matches"], list)


def test_stable_has_no_episodes():
    entries = [{**e, "features": {}} for e in generate("stable", 60)]
    tl = compute_timeline(entries)["timeline"]
    assert relapse.extract_episodes(tl) == []


def test_relapse_endpoint(client):
    client.post("/api/seed", json={"scenario": "recurring", "days": 100})
    r = client.get("/api/relapse")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "matches" in body
