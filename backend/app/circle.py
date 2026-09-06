"""Circle of Care -- opt-in trusted-contact nudges.

Privacy-by-design rules (non-negotiable):
  * OPT-IN only. No contacts exist unless the user adds them.
  * The app NEVER auto-sends anything. It only *prepares* a suggestion and a
    pre-written generic message the user can choose to send themselves.
  * A contact only becomes relevant at their configured tier (2=Connect or
    3=Reach out now); by default only at the Urgent tier.
  * We NEVER share raw data, scores, journal text, or signals with a contact.
    The suggested message is deliberately generic ("might appreciate a
    check-in") -- data minimisation by default.

This closes the "who notices" gap: the people who could help are gently
prompted, while the individual stays fully in control.
"""
from __future__ import annotations

# Generic, non-revealing message the USER can choose to send. No scores, no
# signals, no journal content -- ever.
_NUDGE_TEMPLATE = (
    "Hi {name}, this is a quick hello. I've been using a wellbeing app and set "
    "you as someone I trust. I'd really appreciate a check-in when you have a "
    "moment. Thanks for being in my corner."
)


def build_nudge(tier: int, contacts: list[dict]) -> dict | None:
    """Return an opt-in nudge suggestion for the current tier, or None.

    The result describes WHO the user might reach out to and gives a ready
    generic message. It is purely a suggestion surfaced in the UI; the app
    takes no action on its own.
    """
    if tier < 2 or not contacts:
        return None

    eligible = [c for c in contacts if tier >= int(c.get("notify_tier", 3))]
    if not eligible:
        return None

    suggestions = [
        {
            "id": c.get("id"),
            "name": c["name"],
            "method": c.get("method", "other"),
            "detail": c.get("detail", ""),
            "message": _NUDGE_TEMPLATE.format(name=c["name"]),
        }
        for c in eligible
    ]

    headline = (
        "You're at a higher tier right now. If it feels right, reaching out to "
        "someone you trust can help. Here are the people in your Circle of "
        "Care -- you decide whether and when to message them."
    )
    return {
        "tier": tier,
        "headline": headline,
        "contacts": suggestions,
        "privacy_note": "Aura never contacts anyone for you and never shares "
                        "your data. This is only a private suggestion.",
    }
