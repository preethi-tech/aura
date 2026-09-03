import pytest

from app.safety import CRISIS_RESOURCES, detect_crisis


@pytest.mark.parametrize("text", [
    "I want to die",
    "sometimes I think about killing myself",
    "there is no reason to live anymore",
    "I have been thinking about suicide",
    "I keep wanting to hurt myself",
    "I just can't go on",
])
def test_crisis_language_detected(text):
    assert detect_crisis(text) is True


@pytest.mark.parametrize("text", [
    "I had a great day with friends",
    "I feel tired but okay",
    "I want to diet and exercise more",   # 'diet' must not match 'die'
    "the movie was about a dying star",
    "",
])
def test_non_crisis_language_not_flagged(text):
    assert detect_crisis(text) is False


def test_resources_present():
    assert len(CRISIS_RESOURCES) >= 1
    assert all("contact" in r and "name" in r for r in CRISIS_RESOURCES)
