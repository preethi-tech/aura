"""Safety layer: explicit crisis-language detection and crisis resources.

Design rule: safety NEVER depends on the ML model. If explicit crisis language
is present we surface crisis resources immediately, regardless of the trend
score. The app never auto-dials, auto-reports, or contacts anyone on the
user's behalf -- it only *surfaces* resources. A human is always in the loop.
"""
from __future__ import annotations

import re

# Phrases that should immediately surface crisis resources. Kept explicit and
# conservative on purpose; this is a safety net, not a classifier.
_CRISIS_PATTERNS = [
    r"\bkill(?:ing)?\s+my ?self\b",
    r"\bend(?:ing)?\s+my\s+life\b",
    r"\btake\s+my\s+(?:own\s+)?life\b",
    r"\bwant\s+to\s+die\b",
    r"\bwish\s+i\s+(?:was|were)\s+dead\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bnothing\s+to\s+live\s+for\b",
    r"\bcan'?t\s+go\s+on\b",
    r"\bsuicid(?:e|al)\b",
    r"\bhurt(?:ing)?\s+my ?self\b",
    r"\bharm(?:ing)?\s+my ?self\b",
    r"\bself[-\s]?harm\b",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)


def detect_crisis(text: str) -> bool:
    if not text:
        return False
    return bool(_CRISIS_RE.search(text))


# Crisis resources shown by the app. Region-agnostic defaults; edit for your
# locale. These are widely published public helplines.
CRISIS_RESOURCES = [
    {
        "region": "US",
        "name": "988 Suicide & Crisis Lifeline",
        "contact": "Call or text 988",
        "url": "https://988lifeline.org",
    },
    {
        "region": "US",
        "name": "Crisis Text Line",
        "contact": "Text HOME to 741741",
        "url": "https://www.crisistextline.org",
    },
    {
        "region": "International",
        "name": "Find A Helpline (global directory)",
        "contact": "Search your country's helpline",
        "url": "https://findahelpline.com",
    },
]
