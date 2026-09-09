"""Engagement-decline detection (writing-withdrawal signal).

Clinically, one of the earliest and most reliable warning signs is that people
*write less, shorter, and less often* -- they disengage BEFORE they express
distress. Sentiment-only systems miss this withdrawal phase entirely, which is
often the most actionable window (and the point at which a struggling person
stops producing any negative text to analyse -- there is only absence).

This module scores the *act* of journaling (metadata), not its content:
  * word-count drop        -- shorter entries than the personal baseline
  * vocabulary compression -- lower lexical diversity
  * completion drop        -- fewer check-ins per day (gaps / silence)

The word-count signal is ALSO fused into the Aura Index (see analysis.SIGNALS);
this module provides the dedicated, human-readable "withdrawal" readout.
"""
from __future__ import annotations

from datetime import date

WITHDRAWAL_THRESHOLD = 30.0  # engagement_deviation above this == withdrawal


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def _window_stats(entries: list[dict], span_days: int) -> dict:
    """Aggregate journaling stats for a set of entries over ``span_days``."""
    wcs, divs = [], []
    for e in entries:
        text = (e.get("journal_text") or "").strip()
        feats = e.get("features") or {}
        wc = feats.get("word_count")
        if wc is None:
            wc = len(text.split())
        if wc > 0:
            wcs.append(wc)
            toks = text.lower().split()
            divs.append(len(set(toks)) / wc if toks else 0.0)
    completion = len(entries) / span_days if span_days else 0.0
    return {
        "avg_word_count": _mean(wcs),
        "avg_vocab_diversity": _mean(divs),
        "completion_rate": min(1.0, completion),
        "n": len(entries),
    }


def _partition(entries: list[dict], recent_days: int, baseline_days: int):
    """Split entries into a recent window and a prior baseline window by date."""
    dated = [e for e in entries if e.get("date")]
    if not dated:
        return [], []
    last = date.fromisoformat(dated[-1]["date"])
    recent, baseline = [], []
    for e in dated:
        gap = (last - date.fromisoformat(e["date"])).days
        if gap < recent_days:
            recent.append(e)
        elif gap < recent_days + baseline_days:
            baseline.append(e)
    return recent, baseline


def compute(entries: list[dict], *, recent_days: int = 14,
            baseline_days: int = 30) -> dict:
    """Return an engagement / withdrawal readout, or available=False if sparse."""
    recent, baseline = _partition(entries, recent_days, baseline_days)
    if len(recent) < 2 or len(baseline) < 3:
        return {"available": False,
                "message": "Keep checking in -- withdrawal detection needs a "
                           "little more history."}

    cur = _window_stats(recent, recent_days)
    base = _window_stats(baseline, baseline_days)

    wc_drop = 1.0 - (cur["avg_word_count"] / (base["avg_word_count"] + 1e-6))
    comp_drop = base["completion_rate"] - cur["completion_rate"]
    div_drop = 1.0 - (cur["avg_vocab_diversity"] / (base["avg_vocab_diversity"] + 1e-6))

    dev = max(0.0, wc_drop * 0.6 + comp_drop * 0.3 + div_drop * 0.1) * 100.0
    dev = round(min(100.0, dev), 1)

    return {
        "available": True,
        "engagement_deviation": dev,
        "withdrawal": dev > WITHDRAWAL_THRESHOLD,
        "word_count_now": round(cur["avg_word_count"], 1),
        "word_count_baseline": round(base["avg_word_count"], 1),
        "completion_now": round(cur["completion_rate"], 2),
        "completion_baseline": round(base["completion_rate"], 2),
        "message": _message(dev, wc_drop, comp_drop),
    }


def _message(dev: float, wc_drop: float, comp_drop: float) -> str:
    if dev <= WITHDRAWAL_THRESHOLD:
        return ("Your journaling engagement looks steady -- you're showing up "
                "and writing at your usual depth.")
    parts = []
    if wc_drop > 0.25:
        parts.append(f"entries are ~{round(wc_drop*100)}% shorter than usual")
    if comp_drop > 0.15:
        parts.append("you've been checking in less often")
    detail = " and ".join(parts) if parts else "your journaling has dropped off"
    return (f"Heads-up: {detail}. Withdrawing from journaling can itself be an "
            f"early signal -- even a one-line check-in helps.")
