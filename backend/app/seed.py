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
    "So tired. Couldn't focus.",
    "Stayed in again. No energy for anyone.",
    "Drained and empty. Putting everything off.",
    "Didn't sleep. Anxious, too much.",
]
# As decline deepens people write LESS -- terse, withdrawn entries. This is the
# engagement/withdrawal signal in action (Feature 2), while the words that
# remain still carry negative/absolutist tone.
_SEVERE = [
    "Exhausted. Pointless.",
    "Alone. Numb.",
    "Can't. Worthless.",
    "Nothing. Always tired.",
]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _bump(i: int, center: int, width: float, peak: float) -> float:
    """A smooth Gaussian-like severity bump centered on day ``center``."""
    x = (i - center) / max(1.0, width)
    return peak * (2.718281828 ** (-(x * x)))


def _severity_curve(scenario: str, days: int) -> list[float]:
    """Per-day severity in [0,1]: 0 healthy, 1 severe. Drives all signals so
    scenarios stay internally consistent across active + passive channels."""
    if scenario == "stable":
        return [0.0] * days
    if scenario == "recurring":
        # An earlier episode that recovers, then a fresh (current) episode.
        c1 = int(days * 0.30)
        c2 = days - 1
        out = []
        for i in range(days):
            s = max(_bump(i, c1, days * 0.09, 0.8),
                    _bump(i, c2, days * 0.12, 0.85))
            out.append(min(1.0, s))
        return out
    # default: "decline" -- stable, then a sustained ramp to the present.
    decline_start = int(days * 0.58)
    span = max(1, days - decline_start - 1)
    return [0.0 if i < decline_start else min(1.0, (i - decline_start) / span)
            for i in range(days)]


def generate(scenario: str = "decline", days: int = 60) -> list[dict]:
    rng = random.Random(42)  # reproducible
    today = date.today()
    start = today - timedelta(days=days - 1)
    severity = _severity_curve(scenario, days)

    entries: list[dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        s = severity[i]

        if s < 0.12:
            sleep = round(rng.gauss(7.6, 0.35), 1)
            social = rng.randint(3, 6)
            energy = rng.randint(4, 5)
            text = rng.choice(_STABLE_JOURNALS)
            steps = max(200, round(rng.gauss(8500, 900)))
            active = max(0, round(rng.gauss(45, 10)))
            screen = max(30, round(rng.gauss(210, 35)))
        else:
            sleep = round(_lerp(7.5, 4.3, s) + rng.gauss(0, 0.35), 1)
            social = max(0, round(_lerp(4.5, 0.4, s) + rng.gauss(0, 0.6)))
            energy = max(1, min(5, round(_lerp(4.1, 1.4, s) + rng.gauss(0, 0.4))))
            pool = _MILD if s < 0.4 else _MODERATE if s < 0.72 else _SEVERE
            text = rng.choice(pool)
            # Passive signals drift in step with the behavioral decline.
            steps = max(200, round(_lerp(8500, 2200, s) + rng.gauss(0, 700)))
            active = max(0, round(_lerp(45, 8, s) + rng.gauss(0, 8)))
            screen = max(30, round(_lerp(210, 430, s) + rng.gauss(0, 35)))

        entries.append({
            "date": d.isoformat(),
            "journal_text": text,
            "sleep_hours": max(0.0, min(24.0, sleep)),
            "social_count": int(social),
            "energy": int(energy),
            "steps": int(steps),
            "active_minutes": int(active),
            "screen_time_min": int(screen),
        })
    return entries


def generate_interventions(scenario: str = "decline",
                           days: int = 60) -> list[dict]:
    """Seed a plausible intervention-effectiveness history so Feature 3 shows
    'what works for you' immediately in the demo. Deltas are index changes
    (negative == the index dropped == it helped)."""
    today = date.today()
    start = today - timedelta(days=days - 1)

    def on(day_offset):
        return (start + timedelta(days=day_offset)).isoformat()

    # key, list of (day_offset, index_before, index_after)
    plan = [
        ("social_count", [(int(days * 0.62), 55, 46), (int(days * 0.75), 62, 55)]),
        ("sleep_hours", [(int(days * 0.66), 58, 52), (int(days * 0.8), 64, 59)]),
        ("screen_time_min", [(int(days * 0.7), 60, 56)]),
        ("neg_sentiment", [(int(days * 0.72), 61, 58), (int(days * 0.85), 66, 63)]),
        ("energy", [(int(days * 0.78), 63, 63)]),
    ]
    out: list[dict] = []
    for key, trials in plan:
        for off, before, after in trials:
            if off >= days:
                continue
            out.append({
                "date": on(off),
                "intervention_key": key,
                "index_before": float(before),
                "index_after": float(after),
            })
    return out


def generate_assessments(scenario: str = "decline", days: int = 60) -> list[dict]:
    """Periodic PHQ-9 / GAD-7 totals that rise with the decline (ground truth).

    Returned as {date, instrument, total}. Severity is derived downstream.
    """
    today = date.today()
    start = today - timedelta(days=days - 1)
    severity = _severity_curve(scenario, days)

    # Assessment days: every 10 days plus the final day.
    idxs = sorted(set(list(range(0, days, 10)) + [days - 1]))
    out: list[dict] = []
    for i in idxs:
        d = (start + timedelta(days=i)).isoformat()
        s = severity[i]
        phq = round(_lerp(4, 17, s))
        gad = round(_lerp(3, 15, s))
        out.append({"date": d, "instrument": "PHQ-9",
                    "total": max(0, min(27, phq))})
        out.append({"date": d, "instrument": "GAD-7",
                    "total": max(0, min(21, gad))})
    return out
