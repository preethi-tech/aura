"""Tests for engagement-decline (writing-withdrawal) detection."""
from datetime import date, timedelta

from app import engagement


def _entries(word_counts, start=None):
    """Build entries with given per-day word counts (real dates, oldest first)."""
    start = start or (date.today() - timedelta(days=len(word_counts) - 1))
    out = []
    for i, wc in enumerate(word_counts):
        d = start + timedelta(days=i)
        text = " ".join(f"word{j}" for j in range(wc)) if wc else ""
        out.append({
            "date": d.isoformat(),
            "journal_text": text,
            "features": {"word_count": wc},
        })
    return out


def test_engagement_needs_history():
    out = engagement.compute(_entries([20, 18]))
    assert out["available"] is False


def test_steady_engagement_not_flagged():
    # 44 days of consistent ~20-word entries -> no withdrawal.
    out = engagement.compute(_entries([20] * 44))
    assert out["available"] is True
    assert out["withdrawal"] is False
    assert out["engagement_deviation"] <= engagement.WITHDRAWAL_THRESHOLD


def test_withdrawal_detected_on_shrinking_entries():
    # 30 baseline days of long entries, then 14 recent days of near-silence.
    words = [25] * 30 + [3] * 14
    out = engagement.compute(_entries(words))
    assert out["available"] is True
    assert out["withdrawal"] is True
    assert out["word_count_now"] < out["word_count_baseline"]


def test_engagement_endpoint(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    r = client.get("/api/engagement")
    assert r.status_code == 200
    assert r.json()["available"] is True


def test_engagement_in_status(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    s = client.get("/api/status").json()
    assert s["engagement"] is not None
    assert "engagement_deviation" in s["engagement"]
