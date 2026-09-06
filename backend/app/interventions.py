"""Micro-intervention suggestions.

When the Aura Index crosses the "Notice"/"Connect" tiers we surface ONE small,
concrete, evidence-based action mapped to the signal that is contributing most.
These are self-care nudges grounded in behavioural-activation and sleep-hygiene
literature -- deliberately NOT medical advice, NOT therapy, and never presented
as treatment. The goal is to close the loop from *detection* to a gentle,
optional *action* without overstepping.
"""
from __future__ import annotations

# Evidence-based micro-actions keyed by the signal driving the elevation.
# Each is a 2-5 minute action a person can choose to do right now.
_LIBRARY: dict[str, dict] = {
    "sleep_hours": {
        "title": "Wind-down cue",
        "action": "Pick a fixed lights-out time tonight and put screens away "
                  "30 minutes before it.",
        "duration": "tonight",
        "rationale": "Consistent sleep timing is one of the most reliable ways "
                     "to stabilise mood and energy.",
    },
    "screen_time_min": {
        "title": "Screen boundary",
        "action": "Set a 20-minute timer, put the phone in another room, and "
                  "do one offline thing you enjoy.",
        "duration": "20 min",
        "rationale": "Brief, deliberate breaks from passive scrolling reduce "
                     "rumination and free up attention.",
    },
    "steps": {
        "title": "Movement snack",
        "action": "Take a 10-minute walk outside, ideally somewhere with a "
                  "little daylight.",
        "duration": "10 min",
        "rationale": "Short bouts of light activity and daylight lift energy "
                     "and are a core part of behavioural activation.",
    },
    "active_minutes": {
        "title": "Gentle activity",
        "action": "Do 5 minutes of easy stretching or a slow walk around the "
                  "block.",
        "duration": "5 min",
        "rationale": "Any movement counts; small wins rebuild momentum when "
                     "energy is low.",
    },
    "social_count": {
        "title": "One small reconnect",
        "action": "Send a one-line message to someone you trust -- no agenda, "
                  "just hello.",
        "duration": "2 min",
        "rationale": "Light social contact is protective; a tiny reach-out "
                     "often breaks a withdrawal spiral.",
    },
    "energy": {
        "title": "Two-minute activation",
        "action": "Choose the smallest useful task (a glass of water, opening "
                  "a window) and do just that.",
        "duration": "2 min",
        "rationale": "Starting with a trivially small action is a proven way "
                     "to overcome low-energy inertia.",
    },
    "neg_sentiment": {
        "title": "Box breathing",
        "action": "Breathe in for 4, hold 4, out 4, hold 4 -- repeat for 2 "
                  "minutes.",
        "duration": "2 min",
        "rationale": "Slow paced breathing calms the stress response and eases "
                     "a spiral of negative thoughts.",
    },
    "first_person_ratio": {
        "title": "Zoom out",
        "action": "Write one sentence about something outside yourself you "
                  "noticed today.",
        "duration": "2 min",
        "rationale": "Shifting attention outward gently counters the "
                     "self-focused rumination that tracks low mood.",
    },
    "absolutist_ratio": {
        "title": "Soften an absolute",
        "action": "Take one 'always/never' thought and rewrite it with "
                  "'sometimes' or 'right now'.",
        "duration": "2 min",
        "rationale": "Loosening all-or-nothing language is a simple, evidence "
                     "based cognitive reframing step.",
    },
    "future_focus_ratio": {
        "title": "Tiny plan",
        "action": "Name one small thing you're mildly looking forward to in "
                  "the next few days.",
        "duration": "2 min",
        "rationale": "Reconnecting with even minor future plans supports mood "
                     "and motivation.",
    },
}

# A calm-tier affirmation shown when things look stable (keeps the loop kind).
_STABLE = {
    "key": "maintain",
    "title": "Keep it up",
    "action": "Your patterns look steady. Note one thing that's working so you "
              "can lean on it later.",
    "duration": "1 min",
    "rationale": "Reinforcing what already helps makes it easier to return to "
                 "when things get harder.",
}


def suggest(tier: int, top_signals: list[dict], *, max_items: int = 2) -> list[dict]:
    """Return up to ``max_items`` micro-interventions for the current state.

    * tier 0  -> a single gentle 'maintain' affirmation
    * tier 1+ -> actions targeting the top contributing signals
    """
    if tier <= 0 or not top_signals:
        return [dict(_STABLE)]

    out: list[dict] = []
    seen: set[str] = set()
    for sig in top_signals:
        key = sig.get("key")
        item = _LIBRARY.get(key)
        if item and key not in seen:
            out.append({"key": key, **item})
            seen.add(key)
        if len(out) >= max_items:
            break

    # Fallback so an elevated tier always offers at least one action.
    if not out:
        out.append({"key": "neg_sentiment", **_LIBRARY["neg_sentiment"]})
    return out
