"""Validated self-report questionnaires: PHQ-9 (depression) and GAD-7 (anxiety).

These provide *ground truth* for the evaluation harness and let a user track a
recognized clinical measure alongside the passive Aura Index. Scoring follows
the standard published cut-points. This is a self-awareness aid, not a
diagnosis.
"""
from __future__ import annotations

# Response options (shared by both instruments): 0..3
RESPONSE_OPTIONS = [
    (0, "Not at all"),
    (1, "Several days"),
    (2, "More than half the days"),
    (3, "Nearly every day"),
]

PHQ9_ITEMS = [
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble falling/staying asleep, or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself, or that you are a failure",
    "Trouble concentrating on things",
    "Moving/speaking slowly, or being restless and fidgety",
    "Thoughts that you would be better off dead, or of hurting yourself",
]

GAD7_ITEMS = [
    "Feeling nervous, anxious, or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it is hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid, as if something awful might happen",
]

INSTRUMENTS = {
    "PHQ-9": {"items": PHQ9_ITEMS, "max": 27, "case_threshold": 10},
    "GAD-7": {"items": GAD7_ITEMS, "max": 21, "case_threshold": 10},
}


def severity_band(instrument: str, total: int) -> str:
    if instrument == "PHQ-9":
        return (
            "minimal" if total <= 4 else
            "mild" if total <= 9 else
            "moderate" if total <= 14 else
            "moderately severe" if total <= 19 else
            "severe"
        )
    # GAD-7
    return (
        "minimal" if total <= 4 else
        "mild" if total <= 9 else
        "moderate" if total <= 14 else
        "severe"
    )


def score(instrument: str, *, responses: list[int] | None = None,
          total: int | None = None) -> dict:
    """Score an assessment from item responses or a precomputed total.

    Returns total, severity band, case-threshold flag, and (for PHQ-9) whether
    the self-harm item was endorsed.
    """
    if instrument not in INSTRUMENTS:
        raise ValueError(f"unknown instrument: {instrument}")
    meta = INSTRUMENTS[instrument]

    item9_flag = False
    if responses is not None:
        if len(responses) != len(meta["items"]):
            raise ValueError(
                f"{instrument} expects {len(meta['items'])} responses"
            )
        if any(r < 0 or r > 3 for r in responses):
            raise ValueError("responses must be in 0..3")
        total = sum(responses)
        if instrument == "PHQ-9":
            item9_flag = responses[8] >= 1  # self-harm item endorsed
    if total is None:
        raise ValueError("provide either responses or total")
    total = max(0, min(meta["max"], int(total)))

    return {
        "instrument": instrument,
        "total": total,
        "max": meta["max"],
        "severity": severity_band(instrument, total),
        "case_threshold": meta["case_threshold"],
        "is_case": total >= meta["case_threshold"],
        "item9_flag": item9_flag,
    }
