"""The Aura analysis engine.

Core ideas (see README):
  * PERSONALIZED baselines -- every signal is normalized against the user's own
    recent history (robust median / MAD), never a population norm.
  * TREND, not single points -- we only count *concerning* deviations and then
    smooth over a window, so one bad day does not raise an alert; sustained,
    multi-signal drift does.
  * FUSION -- weak signals (sleep, social contact, energy, journal tone,
    self-focus, absolutist language) are fused into one 0-100 Aura Index.
  * EXPLAINABILITY -- every score decomposes into per-signal contributions.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Tunables ---------------------------------------------------------------
BASELINE_WINDOW = 21      # look back this many prior days for the baseline
MIN_HISTORY = 10          # no scoring until this many prior days exist
MIN_BASELINE_POINTS = 7   # min non-null points to baseline a single signal
SMOOTH_WINDOW = 5         # rolling window that enforces "sustained" drift
DEV_CAP = 4.0             # clamp per-signal z so outliers can't dominate
SATURATION_C = 3.0        # maps smoothed risk -> 0..100 (higher = gentler)

TIER_THRESHOLDS = [25.0, 50.0, 75.0]  # index cut points for tiers 1,2,3

TIER_LABELS = {
    0: "Stable",
    1: "Notice",
    2: "Connect",
    3: "Reach out now",
}
TIER_MESSAGES = {
    0: "Your patterns look close to your own baseline.",
    1: "A few signals have drifted. A small self-check-in might help.",
    2: "Several signals have shifted together for a while. Consider reaching "
       "out to someone you trust.",
    3: "Your signals suggest a sustained, significant shift. Please consider "
       "contacting support now -- you don't have to handle this alone.",
}


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    direction: str   # "low" or "high" is the concerning direction
    weight: float
    min_scale: float
    message: str


SIGNALS: list[Signal] = [
    # min_scale = the smallest "normal" day-to-day variation for each signal, so
    # ordinary fluctuation does not produce large z-scores / false alerts.
    Signal("sleep_hours", "Sleep", "low", 1.0, 1.0,
           "Sleep has dropped below your usual pattern."),
    Signal("social_count", "Social contact", "low", 1.2, 1.2,
           "You've been connecting with others less than usual."),
    Signal("energy", "Energy", "low", 1.0, 0.8,
           "Energy has been lower than your typical range."),
    Signal("neg_sentiment", "Journal tone", "high", 1.3, 0.12,
           "Journal tone has been more negative than usual."),
    Signal("first_person_ratio", "Self-focus", "high", 0.8, 0.06,
           "Writing has become more self-focused (more \u201cI/me\u201d)."),
    Signal("absolutist_ratio", "Absolutist words", "high", 0.9, 0.04,
           "More absolute words (\u201calways/never\u201d) than usual."),
    Signal("future_focus_ratio", "Future orientation", "low", 0.7, 0.06,
           "Writing shows less looking-ahead / planning than usual."),
]
_SIGNAL_BY_KEY = {s.key: s for s in SIGNALS}


# --- Small robust-stats helpers (stdlib only) -------------------------------
def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _mad(xs: list[float], med: float) -> float:
    return _median([abs(x - med) for x in xs])


def _signal_value(entry: dict, key: str) -> float | None:
    if key in ("sleep_hours", "social_count", "energy"):
        v = entry.get(key)
    else:
        v = entry.get("features", {}).get(key)
    return None if v is None else float(v)


def _tier_for_index(index: float) -> int:
    for tier, thr in enumerate(TIER_THRESHOLDS, start=1):
        if index < thr:
            return tier - 1
    return 3


def compute_timeline(entries: list[dict]) -> dict:
    """Compute the full per-day analysis series plus a latest-status summary."""
    n = len(entries)
    daily: list[dict] = []

    for i, entry in enumerate(entries):
        prior = entries[max(0, i - BASELINE_WINDOW):i]
        contributions: dict[str, float] = {s.key: 0.0 for s in SIGNALS}
        raw = 0.0
        calibrating = i < MIN_HISTORY

        # No scoring until a baseline exists -- avoids early false alerts.
        if not calibrating:
            for sig in SIGNALS:
                x = _signal_value(entry, sig.key)
                if x is None:
                    continue
                prior_vals = [
                    v for v in (_signal_value(e, sig.key) for e in prior)
                    if v is not None
                ]
                if len(prior_vals) < MIN_BASELINE_POINTS:
                    continue
                med = _median(prior_vals)
                scale = max(1.4826 * _mad(prior_vals, med), sig.min_scale)
                z = (x - med) / scale
                dev = z if sig.direction == "high" else -z
                dev = max(0.0, min(dev, DEV_CAP))
                contrib = sig.weight * dev
                contributions[sig.key] = round(contrib, 4)
                raw += contrib

        daily.append({
            "date": entry["date"],
            "raw": round(raw, 4),
            "contributions": contributions,
            "safety_flag": bool(entry.get("safety_flag")),
            "calibrating": i < MIN_HISTORY,
            # echo raw signals for charts / transparency
            "sleep_hours": entry.get("sleep_hours"),
            "social_count": entry.get("social_count"),
            "energy": entry.get("energy"),
            "neg_sentiment": entry.get("features", {}).get("neg_sentiment"),
            "reflection": entry.get("features", {}).get("reflection"),
        })

    # Smooth the raw risk into the sustained Aura Index.
    for i, day in enumerate(daily):
        window = daily[max(0, i - SMOOTH_WINDOW + 1):i + 1]
        smoothed = sum(d["raw"] for d in window) / len(window)
        index = 100.0 * smoothed / (smoothed + SATURATION_C)
        day["aura_index"] = round(index, 1)
        tier = _tier_for_index(index)
        if day["safety_flag"]:
            tier = 3
        day["tier"] = tier

    summary = _summarize(daily, n)
    return {"timeline": daily, "summary": summary, "signals": [
        {"key": s.key, "label": s.label} for s in SIGNALS
    ]}


def _summarize(daily: list[dict], entry_count: int) -> dict:
    if not daily:
        return {
            "has_data": False, "calibrating": True, "aura_index": None,
            "tier": None, "tier_label": None, "tier_message": None,
            "safety_alert": False, "top_signals": [], "latest_date": None,
            "entry_count": 0,
        }

    latest = daily[-1]
    # Average each signal's contribution across the smoothing window for a
    # stable "why" explanation.
    window = daily[-SMOOTH_WINDOW:]
    avg_contrib: dict[str, float] = {}
    for sig in SIGNALS:
        vals = [d["contributions"].get(sig.key, 0.0) for d in window]
        avg_contrib[sig.key] = sum(vals) / len(vals)

    ranked = sorted(avg_contrib.items(), key=lambda kv: kv[1], reverse=True)
    top_signals = [
        {
            "key": key,
            "label": _SIGNAL_BY_KEY[key].label,
            "contribution": round(val, 3),
            "message": _SIGNAL_BY_KEY[key].message,
        }
        for key, val in ranked if val > 0.05
    ][:3]

    tier = latest["tier"]
    return {
        "has_data": True,
        "calibrating": latest["calibrating"],
        "aura_index": latest["aura_index"],
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "tier_message": TIER_MESSAGES[tier],
        "safety_alert": bool(latest["safety_flag"]),
        "top_signals": top_signals,
        "latest_date": latest["date"],
        "entry_count": entry_count,
        "reflection": latest.get("reflection"),
    }
