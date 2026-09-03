import pytest

from app.assessments import GAD7_ITEMS, PHQ9_ITEMS, score, severity_band


def test_phq9_all_zero_is_minimal():
    r = score("PHQ-9", responses=[0] * 9)
    assert r["total"] == 0
    assert r["severity"] == "minimal"
    assert r["is_case"] is False
    assert r["item9_flag"] is False


def test_phq9_item9_flag():
    responses = [0] * 8 + [2]  # only self-harm item endorsed
    r = score("PHQ-9", responses=responses)
    assert r["item9_flag"] is True


def test_phq9_severity_bands():
    assert severity_band("PHQ-9", 4) == "minimal"
    assert severity_band("PHQ-9", 9) == "mild"
    assert severity_band("PHQ-9", 14) == "moderate"
    assert severity_band("PHQ-9", 19) == "moderately severe"
    assert severity_band("PHQ-9", 27) == "severe"


def test_gad7_max_is_severe():
    r = score("GAD-7", responses=[3] * len(GAD7_ITEMS))
    assert r["total"] == 21
    assert r["severity"] == "severe"
    assert r["is_case"] is True


def test_score_from_total_only():
    r = score("PHQ-9", total=12)
    assert r["total"] == 12
    assert r["severity"] == "moderate"
    assert r["is_case"] is True


def test_wrong_response_length_raises():
    with pytest.raises(ValueError):
        score("PHQ-9", responses=[0, 1, 2])


def test_unknown_instrument_raises():
    with pytest.raises(ValueError):
        score("BDI", total=5)


def test_item_counts():
    assert len(PHQ9_ITEMS) == 9
    assert len(GAD7_ITEMS) == 7
