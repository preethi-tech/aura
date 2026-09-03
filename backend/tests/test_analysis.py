from datetime import date, timedelta

from app.analysis import MIN_HISTORY, compute_timeline
from app.features import extract_deterministic


def _entry(i, sleep, social, energy, text="", safety=False):
    d = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
    return {
        "date": d,
        "journal_text": text,
        "sleep_hours": sleep,
        "social_count": social,
        "energy": energy,
        "features": extract_deterministic(text),
        "safety_flag": safety,
    }


def _stable(n):
    return [_entry(i, 7.5, 4, 4) for i in range(n)]


def test_calibrating_period_does_not_score():
    entries = _stable(MIN_HISTORY - 1)
    s = compute_timeline(entries)["summary"]
    assert s["calibrating"] is True
    assert s["aura_index"] == 0.0


def test_at_baseline_is_low():
    entries = _stable(20)
    s = compute_timeline(entries)["summary"]
    assert s["calibrating"] is False
    assert s["aura_index"] < 25  # tier 0


def test_single_bad_day_stays_lower_than_sustained_decline():
    base = _stable(15)
    one_bad = base + [_entry(15, 4.0, 0, 1)]
    sustained = base + [_entry(15 + k, 4.0, 0, 1) for k in range(6)]

    idx_one = compute_timeline(one_bad)["summary"]["aura_index"]
    idx_sustained = compute_timeline(sustained)["summary"]["aura_index"]

    assert idx_one < idx_sustained
    assert idx_sustained >= 50  # sustained multi-signal drift -> tier 2+


def test_safety_flag_forces_top_tier():
    entries = _stable(15) + [_entry(15, 7.5, 4, 4, safety=True)]
    s = compute_timeline(entries)["summary"]
    assert s["tier"] == 3
    assert s["safety_alert"] is True


def test_top_signals_explain_decline():
    entries = _stable(15) + [_entry(15 + k, 4.0, 0, 1) for k in range(6)]
    s = compute_timeline(entries)["summary"]
    labels = {sig["label"] for sig in s["top_signals"]}
    # sleep / social / energy all collapsed -> should appear in the explanation
    assert labels & {"Sleep", "Social contact", "Energy"}
