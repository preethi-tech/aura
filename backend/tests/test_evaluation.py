from app.analysis import compute_timeline
from app.evaluation import evaluate
from app.features import extract_deterministic
from app.seed import generate, generate_assessments


def _build_timeline():
    entries = []
    for e in generate("decline", 60):
        entries.append({
            **e,
            "features": extract_deterministic(e["journal_text"]),
            "safety_flag": False,
        })
    return compute_timeline(entries)["timeline"]


def test_evaluation_unavailable_without_data():
    ev = evaluate([], [])
    assert ev["available"] is False


def test_evaluation_on_demo_is_meaningful():
    tl = _build_timeline()
    ev = evaluate(tl, generate_assessments("decline", 60))
    assert ev["available"] is True
    # Aura Index should positively track the questionnaires.
    assert ev["correlation"]["PHQ-9"] is not None
    assert ev["correlation"]["PHQ-9"] > 0.3
    # Should detect and (on this synthetic decline) warn before the first case.
    assert ev["lead_time_days"] is not None
    assert ev["recall"] == 1.0


def test_detection_not_in_first_week():
    # With calibration + robust floors, detection must not fire immediately.
    tl = _build_timeline()
    ev = evaluate(tl, generate_assessments("decline", 60))
    first_date = tl[0]["date"]
    assert ev["detection_date"] is not None
    assert ev["detection_date"] > first_date
