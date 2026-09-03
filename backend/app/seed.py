"""Synthetic demo-user generator.

Produces a reproducible timeline so the app is demoable with zero real,
sensitive data. The "decline" scenario holds a healthy baseline for ~60% of
the window, then introduces a gradual, multi-signal drift (shorter sleep, less
social contact, lower energy, more negative / self-focused / absolutist / less
future-oriented journaling) -- the sustained pattern the engine catches.

It also emits synthetic PHQ-9 / GAD-7 assessment scores that track the decline,
so the evaluation harness has ground truth to run against out of the box.

No explicit crisis language is used, so the demo showcases *trend-based*
escalation rather than the (separately tested) safety override.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

# Stable-period journals: social, positive, and FUTURE-oriented (planning,
# looking forward) -- future orientation drops away during the decline.
_STABLE_JOURNALS = [
    "Had a good day at work and grabbed dinner with friends. Looking forward to the weekend.",
    "We went for a long walk together and I felt calm and grateful. Planning a trip next month.",
    "Productive morning, then called my family. Feeling hopeful and I'll see them soon.",
    "Met the team for lunch, lots of fun. Tomorrow we're planning a hike together.",
    "Enjoyed a relaxed evening with a friend. We'll catch up again next week.",
    "Great workout, then coffee with a colleague. Excited for the plans this weekend.",
    "Cooked dinner with family, we laughed a lot. Looking forward to game night soon.",
    "Finished a project I'm proud of and celebrated with people I love. Big goals for next quarter.",
]
_MILD = [
    "A bit tired today. Skipped the gym but got through work.",
    "Didn't sleep great. Felt kind of flat but okay.",
    "Quiet day. Meant to call someone back but didn't get to it.",
    "Low energy this afternoon. Nothing much happened.",
]
_MODERATE = [
    "I'm so tired all the time. I couldn't really focus on anything today.",
    "I stayed in again. I never seem to have the energy to see anyone.",
    "I feel drained and kind of empty. I keep putting everything off.",
    "Didn't sleep much. I'm anxious and everything feels like too much.",
]
_SEVERE = [
    "I'm exhausted and everything feels pointless. I always mess things up.",
    "I feel completely alone. Nothing ever gets better and I'm so tired.",
    "I can't sleep. I feel worthless and numb, and it never seems to lift.",
    "I've withdrawn from everyone. It all feels hopeless and empty and I'm always tired.",
]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def generate(scenario: str = "decline", days: int = 60) -> list[dict]:
    rng = random.Random(42)  # reproducible
    today = date.today()
    start = today - timedelta(days=days - 1)
    decline_start = int(days * 0.58)

    entries: list[dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        stable = scenario != "decline" or i < decline_start

        if stable:
            sleep = round(rng.gauss(7.6, 0.35), 1)
            social = rng.randint(3, 6)
            energy = rng.randint(4, 5)
            text = rng.choice(_STABLE_JOURNALS)
        else:
            p = (i - decline_start) / max(1, days - decline_start - 1)
            sleep = round(_lerp(7.5, 4.3, p) + rng.gauss(0, 0.35), 1)
            social = max(0, round(_lerp(4.5, 0.4, p) + rng.gauss(0, 0.6)))
            energy = max(1, min(5, round(_lerp(4.1, 1.4, p) + rng.gauss(0, 0.4))))
            pool = _MILD if p < 0.34 else _MODERATE if p < 0.68 else _SEVERE
            text = rng.choice(pool)

        entries.append({
            "date": d.isoformat(),
            "journal_text": text,
            "sleep_hours": max(0.0, min(24.0, sleep)),
            "social_count": int(social),
            "energy": int(energy),
        })
    return entries


def generate_assessments(scenario: str = "decline", days: int = 60) -> list[dict]:
    """Periodic PHQ-9 / GAD-7 totals that rise with the decline (ground truth).

    Returned as {date, instrument, total}. Severity is derived downstream.
    """
    today = date.today()
    start = today - timedelta(days=days - 1)
    decline_start = int(days * 0.58)
    span = max(1, days - decline_start - 1)

    # Assessment days: every 10 days plus the final day.
    idxs = sorted(set(list(range(0, days, 10)) + [days - 1]))
    out: list[dict] = []
    for i in idxs:
        d = (start + timedelta(days=i)).isoformat()
        if scenario != "decline" or i < decline_start:
            phq, gad = 4, 3
        else:
            p = (i - decline_start) / span
            phq = round(_lerp(4, 17, p))
            gad = round(_lerp(3, 15, p))
        out.append({"date": d, "instrument": "PHQ-9",
                    "total": max(0, min(27, phq))})
        out.append({"date": d, "instrument": "GAD-7",
                    "total": max(0, min(21, gad))})
    return out
