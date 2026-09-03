from app.features import extract_deterministic, extract_features


def test_first_person_and_absolutist_ratios():
    f = extract_deterministic("I always feel like I never really win")
    assert f["first_person_ratio"] > 0      # two 'I'
    assert f["absolutist_ratio"] > 0        # 'always', 'never'
    assert f["word_count"] == 8


def test_future_focus_detected():
    f = extract_deterministic("Tomorrow I will plan the weekend trip soon")
    # tomorrow, will, plan, weekend, soon
    assert f["future_focus_ratio"] > 0.4


def test_future_focus_absent_in_past_tense():
    f = extract_deterministic("I felt tired and empty and worthless today")
    assert f["future_focus_ratio"] == 0.0


def test_empty_text_is_neutral():
    f = extract_deterministic("")
    assert f["word_count"] == 0
    assert f["neg_sentiment"] == 0.5
    assert f["future_focus_ratio"] == 0.0


def test_negative_beats_positive_sentiment():
    neg = extract_deterministic("I feel hopeless, worthless, empty and alone")
    pos = extract_deterministic("I feel grateful, hopeful, calm and happy")
    assert neg["neg_sentiment"] > pos["neg_sentiment"]
    assert neg["neg_sentiment"] > 0.5
    assert pos["neg_sentiment"] < 0.5


def test_extract_features_offline_has_no_reflection():
    # No GEMINI_API_KEY in tests -> deterministic only, no reflection key.
    f = extract_features("A calm and ordinary day")
    assert f["sentiment_source"] == "lexicon"
    assert "reflection" not in f
