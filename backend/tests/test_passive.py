"""Tests for passive signal integration (Google Fit / phone sensors)."""
from app import passive
from app.analysis import compute_timeline


def _mk_entries(n=30):
    return [
        {"date": f"2026-01-{i+1:02d}", "journal_text": "ok",
         "sleep_hours": 7.0, "social_count": 3, "energy": 4,
         "features": {}}
        for i in range(n)
    ]


def test_simulate_fit_is_deterministic():
    entries = _mk_entries(20)
    a = passive.simulate_fit(entries, days=20)
    b = passive.simulate_fit(entries, days=20)
    assert a == b  # same input -> identical output (reproducible)
    assert len(a) == 20
    for row in a:
        assert row["steps"] >= 0
        assert 0 <= row["screen_time_min"] <= 900


def test_sync_passive_falls_back_to_simulation():
    entries = _mk_entries(10)
    rows, source = passive.sync_passive(entries, days=10, access_token=None)
    assert source == "simulated"
    assert len(rows) == 10
    assert all("steps" in r and "screen_time_min" in r for r in rows)


def test_passive_signals_feed_the_index():
    """Low steps + high screen time in the concerning direction should be
    picked up as contributions once a baseline exists."""
    entries = []
    for i in range(30):
        # Healthy baseline then a passive-only decline in the last week.
        declining = i >= 23
        entries.append({
            "date": f"2026-02-{i+1:02d}",
            "journal_text": "a normal day",
            "sleep_hours": 7.2, "social_count": 3, "energy": 4,
            "steps": 2000 if declining else 9000,
            "active_minutes": 5 if declining else 45,
            "screen_time_min": 500 if declining else 200,
            "features": {},
        })
    tl = compute_timeline(entries)
    latest = tl["timeline"][-1]
    contrib = latest["contributions"]
    assert contrib["steps"] > 0
    assert contrib["screen_time_min"] > 0


def test_fit_sync_endpoint(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 40})
    r = client.post("/api/fit/sync", json={"days": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] in ("simulated", "google_fit")
    assert body["synced"] > 0
    # Passive data should now be present on timeline entries.
    tl = client.get("/api/timeline").json()["timeline"]
    assert any(d.get("steps") is not None for d in tl)


def test_fit_sync_requires_entries(client):
    r = client.post("/api/fit/sync", json={"days": 30})
    assert r.status_code == 200
    assert r.json()["synced"] == 0
