"""Tests for explainable AI insights: weekly summary, cycles, forecast."""
from datetime import date, timedelta

from app import insights
from app.analysis import compute_timeline


def _decline_entries(n=45):
    """Healthy first half, declining second half, with real dates."""
    start = date(2026, 3, 1)
    out = []
    for i in range(n):
        d = start + timedelta(days=i)
        declining = i >= n * 0.6
        p = (i - n * 0.6) / max(1, n - n * 0.6)
        out.append({
            "date": d.isoformat(),
            "journal_text": "tired and low" if declining else "good day with friends",
            "sleep_hours": (7.5 - 3 * p) if declining else 7.5,
            "social_count": int(4 - 3 * p) if declining else 4,
            "energy": max(1, int(4 - 2 * p)) if declining else 4,
            "steps": int(8500 - 6000 * p) if declining else 8500,
            "active_minutes": int(45 - 35 * p) if declining else 45,
            "screen_time_min": int(200 + 200 * p) if declining else 200,
            "features": {},
        })
    return out


def test_weekly_summary_reports_facts():
    tl = compute_timeline(_decline_entries())["timeline"]
    ws = insights.weekly_summary(tl)
    assert ws["available"] is True
    assert ws["direction"] in ("rising", "easing", "steady")
    assert isinstance(ws["facts"], list)
    # A decline should surface at least one concerning mover.
    assert len(ws["facts"]) >= 1
    assert ws["narrative"]


def test_weekly_summary_needs_data():
    tl = compute_timeline([])["timeline"]
    ws = insights.weekly_summary(tl)
    assert ws["available"] is False


def test_detect_cycles_weekday_structure():
    tl = compute_timeline(_decline_entries(60))["timeline"]
    cy = insights.detect_cycles(tl)
    assert cy["available"] is True
    assert "by_weekday" in cy
    # hardest_day should be one of the weekday labels
    assert cy["hardest_day"] in insights._WEEKDAYS


def test_forecast_projects_direction():
    tl = compute_timeline(_decline_entries())["timeline"]
    fc = insights.forecast(tl)
    assert fc["available"] is True
    assert fc["trend"] in ("worsening", "improving", "stable")
    assert 0 <= fc["projected"] <= 100
    assert fc["text"]


def test_forecast_insufficient_data():
    tl = compute_timeline(_decline_entries(12))["timeline"]
    # Only a few scored days -> forecast may still work; a tiny set returns
    # unavailable. Use an explicitly tiny timeline to assert the guard.
    fc = insights.forecast([{"date": "2026-01-01", "aura_index": 10,
                             "calibrating": False}])
    assert fc["available"] is False


def test_insights_endpoint(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    r = client.get("/api/insights")
    assert r.status_code == 200
    body = r.json()
    assert "weekly_summary" in body
    assert "cycles" in body
    assert "forecast" in body
    assert body["weekly_summary"]["available"] is True
