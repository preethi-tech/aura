"""Explainable AI insights.

Turns the raw Aura timeline into human-readable understanding:

  * weekly_summary  -- a natural-language recap of the last 7 days grounded in
    concrete numbers (deterministic), optionally rephrased warmly by Gemini.
  * detect_cycles   -- recurring patterns: weekday-vs-weekend dips and the most
    common "low" day, computed deterministically so they are trustworthy.
  * forecast        -- a short-horizon linear projection of the Aura Index
    ("if the current trend continues...") with a plain-language direction.

Everything works fully offline. Gemini, when configured, is used ONLY to make
the deterministic findings read more naturally -- never to invent numbers.
"""
from __future__ import annotations

from datetime import date

from .analysis import SIGNALS, _SIGNAL_BY_KEY
from .config import settings

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _baseline_vs_recent(timeline: list[dict], key: str, recent_n: int = 7):
    """Return (recent_mean, baseline_mean) for a raw signal, or (None, None)."""
    vals = [(d.get(key)) for d in timeline]
    recent = [v for v in vals[-recent_n:] if v is not None]
    baseline = [v for v in vals[:-recent_n] if v is not None]
    return _mean(recent), _mean(baseline)


def weekly_summary(timeline: list[dict]) -> dict:
    """Build a grounded 7-day summary with per-signal deltas + a narrative."""
    scored = [d for d in timeline if not d.get("calibrating")]
    if len(scored) < 3:
        return {"available": False,
                "narrative": "Keep checking in -- a few more days of data will "
                             "unlock your weekly insights."}

    recent = scored[-7:]
    idx_recent = _mean([d["aura_index"] for d in recent]) or 0.0
    idx_prev = _mean([d["aura_index"] for d in scored[-14:-7]])
    direction = "steady"
    if idx_prev is not None:
        if idx_recent > idx_prev + 4:
            direction = "rising"
        elif idx_recent < idx_prev - 4:
            direction = "easing"

    # Per-signal movement vs the user's own baseline.
    facts: list[dict] = []
    for sig in SIGNALS:
        r, b = _baseline_vs_recent(timeline, sig.key)
        if r is None or b is None or b == 0:
            continue
        delta = r - b
        pct = 100.0 * delta / abs(b)
        # Only report movement in the concerning direction that's meaningful.
        concerning = (delta < 0) if sig.direction == "low" else (delta > 0)
        if concerning and abs(pct) >= 12:
            facts.append({
                "key": sig.key,
                "label": sig.label,
                "recent": round(r, 1),
                "baseline": round(b, 1),
                "pct": round(pct),
                "text": _fact_text(sig.key, sig.label, r, b, pct),
            })
    facts.sort(key=lambda f: abs(f["pct"]), reverse=True)
    facts = facts[:3]

    narrative = _compose_narrative(idx_recent, direction, facts)
    gem = _gemini_polish(narrative, facts, direction)
    return {
        "available": True,
        "aura_index_avg": round(idx_recent, 1),
        "direction": direction,
        "facts": facts,
        "narrative": gem or narrative,
        "narrative_source": "gemini" if gem else "deterministic",
    }


def _fact_text(key: str, label: str, recent: float, baseline: float,
               pct: float) -> str:
    arrow = "below" if recent < baseline else "above"
    if key == "sleep_hours":
        return f"sleep averaged {recent:.1f}h, about {abs(recent-baseline):.1f}h {arrow} your usual"
    if key == "steps":
        return f"activity averaged {int(recent):,} steps ({abs(round(pct))}% {arrow} baseline)"
    if key == "screen_time_min":
        return f"screen time averaged {int(recent)} min/day ({abs(round(pct))}% {arrow} baseline)"
    if key == "social_count":
        return f"social contact averaged {recent:.1f}/day ({abs(round(pct))}% {arrow} usual)"
    if key == "energy":
        return f"energy averaged {recent:.1f}/5 ({arrow} your usual)"
    return f"{label.lower()} was {abs(round(pct))}% {arrow} your baseline"


def _compose_narrative(idx: float, direction: str, facts: list[dict]) -> str:
    lead = {
        "rising": "Your Aura Index has been rising this week",
        "easing": "Your Aura Index has been easing this week",
        "steady": "Your Aura Index has held fairly steady this week",
    }[direction]
    lead += f" (7-day average {idx:.0f}/100)."
    if not facts:
        return lead + " No single signal stands out from your baseline."
    joined = "; ".join(f["text"] for f in facts)
    return f"{lead} The main movers: {joined}."


def _compose_cycle_text(cycles: dict) -> str:
    bits = []
    if cycles.get("weekend_effect"):
        we = cycles["weekend_effect"]
        worse = "weekends" if we["weekend_worse"] else "weekdays"
        bits.append(f"your index tends to run higher on {worse}")
    if cycles.get("hardest_day"):
        bits.append(f"{cycles['hardest_day']} is often your toughest day")
    return "; ".join(bits)


def detect_cycles(timeline: list[dict]) -> dict:
    """Detect weekday/weekend and per-weekday recurring patterns."""
    scored = [d for d in timeline if not d.get("calibrating")
              and d.get("aura_index") is not None]
    if len(scored) < 10:
        return {"available": False}

    by_dow: dict[int, list[float]] = {i: [] for i in range(7)}
    for d in scored:
        dow = date.fromisoformat(d["date"]).weekday()
        by_dow[dow].append(d["aura_index"])

    dow_means = {i: (_mean(v) or 0.0) for i, v in by_dow.items() if v}
    result: dict = {"available": True,
                    "by_weekday": {_WEEKDAYS[i]: round(m, 1)
                                   for i, m in dow_means.items()}}

    weekday = [m for i, m in dow_means.items() if i < 5]
    weekend = [m for i, m in dow_means.items() if i >= 5]
    if weekday and weekend:
        wd, we = _mean(weekday), _mean(weekend)
        if abs(we - wd) >= 5:
            result["weekend_effect"] = {
                "weekday_avg": round(wd, 1),
                "weekend_avg": round(we, 1),
                "weekend_worse": we > wd,
            }

    if dow_means:
        hardest = max(dow_means.items(), key=lambda kv: kv[1])
        result["hardest_day"] = _WEEKDAYS[hardest[0]]

    result["text"] = _compose_cycle_text(result)
    return result


def forecast(timeline: list[dict], horizon: int = 7) -> dict:
    """Project the Aura Index forward with a simple least-squares trend.

    Intentionally simple and transparent: fits a line to the recent scored
    index and extrapolates. Framed as "if the current trend continues" -- a
    directional heads-up, not a clinical prediction.
    """
    scored = [d for d in timeline if not d.get("calibrating")
              and d.get("aura_index") is not None]
    pts = scored[-14:]
    if len(pts) < 5:
        return {"available": False}

    ys = [d["aura_index"] for d in pts]
    xs = list(range(len(ys)))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return {"available": False}
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx

    current = ys[-1]
    projected = intercept + slope * (n - 1 + horizon)
    projected = max(0.0, min(100.0, projected))

    per_week = slope * 7
    if per_week > 3:
        trend = "worsening"
    elif per_week < -3:
        trend = "improving"
    else:
        trend = "stable"

    return {
        "available": True,
        "horizon_days": horizon,
        "current": round(current, 1),
        "projected": round(projected, 1),
        "slope_per_week": round(per_week, 1),
        "trend": trend,
        "text": _forecast_text(trend, projected, horizon),
    }


def _forecast_text(trend: str, projected: float, horizon: int) -> str:
    if trend == "worsening":
        return (f"If the current trend continues, your index could reach "
                f"~{projected:.0f} in {horizon} days. A good moment to lean on "
                f"a small habit or reach out.")
    if trend == "improving":
        return (f"Nice -- the current trend points toward ~{projected:.0f} in "
                f"{horizon} days. Whatever you're doing seems to be helping.")
    return (f"Your index looks stable heading into the next {horizon} days "
            f"(~{projected:.0f}).")


def _gemini_polish(narrative: str, facts: list[dict],
                   direction: str) -> str | None:
    """Ask Gemini to rephrase the grounded facts warmly. Never invents data."""
    if not settings.gemini_enabled or not facts:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        bullet = "\n".join(f"- {f['text']}" for f in facts)
        prompt = (
            "You are a warm, non-clinical wellbeing companion. Rewrite the "
            "following factual weekly summary as 2-3 supportive sentences. "
            "Rules: keep ALL numbers exactly as given, do not invent new "
            "facts, do not diagnose, no clinical terms, be encouraging and "
            f"human.\n\nDirection: {direction}\nFacts:\n{bullet}\n\n"
            f"Draft: {narrative}"
        )
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )
        out = (resp.text or "").strip()
        return out or None
    except Exception:
        return None


def build_insights(timeline: list[dict]) -> dict:
    """Bundle all insight products for the /api/insights endpoint."""
    return {
        "weekly_summary": weekly_summary(timeline),
        "cycles": detect_cycles(timeline),
        "forecast": forecast(timeline),
    }
