"""Linguistic feature extraction.

Two layers:

1. Deterministic, offline features (always computed). These are transparent,
   reproducible counts grounded in the digital-phenotyping literature:
   first-person-singular pronoun ratio, absolutist-word ratio, social-reference
   ratio, and a lexicon sentiment estimate.

2. Optional Gemini enrichment (only if GEMINI_API_KEY is set). Gemini refines
   the negative-sentiment estimate. The objective *counts* are always kept from
   the deterministic layer so the analysis stays explainable and works offline.
"""
from __future__ import annotations

import json
import re

from .config import settings

# --- Lexicons ---------------------------------------------------------------
FIRST_PERSON_SINGULAR = {
    "i", "me", "my", "mine", "myself", "i'm", "i've", "i'll", "i'd",
}
# Al-Mosaiwi & Johnson-Laird (2018) style absolutist markers.
ABSOLUTIST = {
    "absolutely", "all", "always", "complete", "completely", "constant",
    "constantly", "definitely", "entire", "entirely", "ever", "every",
    "everyone", "everything", "everywhere", "full", "fully", "must", "never",
    "nobody", "none", "nothing", "nowhere", "totally", "total", "whole",
    "only",
}
SOCIAL = {
    "friend", "friends", "family", "we", "us", "our", "together", "talk",
    "talked", "call", "called", "meet", "met", "party", "people", "dinner",
    "lunch", "hang", "hung", "group", "team", "visit", "visited", "chat",
    "chatted", "colleague", "colleagues",
}
NEGATIVE = {
    "sad", "down", "low", "tired", "exhausted", "drained", "hopeless",
    "worthless", "empty", "numb", "lonely", "alone", "anxious", "worried",
    "stressed", "overwhelmed", "cry", "crying", "tears", "useless", "failure",
    "failing", "hate", "angry", "dark", "pointless", "meaningless", "guilty",
    "ashamed", "afraid", "scared", "dread", "restless", "insomnia", "awful",
    "terrible", "miserable", "unmotivated", "isolated", "withdrawn", "cant",
    "can't",
}
POSITIVE = {
    "happy", "glad", "good", "great", "joy", "enjoyed", "grateful", "thankful",
    "hopeful", "excited", "calm", "relaxed", "proud", "love", "loved", "fun",
    "better", "energized", "motivated", "connected", "peaceful", "content",
    "optimistic", "accomplished", "wonderful",
}
# Prospective / future-oriented language. Reduced future orientation is
# associated with depression, so LOW future-focus is the concerning direction.
FUTURE_FOCUS = {
    "will", "tomorrow", "soon", "plan", "plans", "planning", "future", "next",
    "upcoming", "later", "hope", "hoping", "forward", "goal", "goals",
    "weekend", "gonna", "shall", "i'll", "we'll", "tonight",
}

_WORD_RE = re.compile(r"[a-z']+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def extract_deterministic(text: str) -> dict:
    words = _tokenize(text)
    wc = len(words)
    if wc == 0:
        return {
            "word_count": 0,
            "first_person_ratio": 0.0,
            "absolutist_ratio": 0.0,
            "social_ratio": 0.0,
            "future_focus_ratio": 0.0,
            "neg_sentiment": 0.5,
            "sentiment_source": "empty",
        }

    fp = sum(1 for w in words if w in FIRST_PERSON_SINGULAR)
    ab = sum(1 for w in words if w in ABSOLUTIST)
    so = sum(1 for w in words if w in SOCIAL)
    fut = sum(1 for w in words if w in FUTURE_FOCUS)
    neg = sum(1 for w in words if w in NEGATIVE)
    pos = sum(1 for w in words if w in POSITIVE)

    neg_density = neg / wc
    pos_density = pos / wc
    # Map lexicon balance into a 0..1 negative-sentiment estimate.
    neg_sentiment = 0.5 + (neg_density - pos_density) * 6.0
    neg_sentiment = max(0.0, min(1.0, neg_sentiment))

    return {
        "word_count": wc,
        "first_person_ratio": round(fp / wc, 4),
        "absolutist_ratio": round(ab / wc, 4),
        "social_ratio": round(so / wc, 4),
        "future_focus_ratio": round(fut / wc, 4),
        "neg_sentiment": round(neg_sentiment, 4),
        "sentiment_source": "lexicon",
    }


def _gemini_sentiment(text: str) -> float | None:
    """Ask Gemini for a calibrated negative-sentiment score in [0, 1].

    Returns None on any failure so the caller falls back to the lexicon score.
    """
    if not settings.gemini_enabled or not text.strip():
        return None
    try:
        from google import genai  # imported lazily; optional dependency
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = (
            "You are a careful, non-clinical text analyst. Read the personal "
            "journal entry and estimate its overall NEGATIVE emotional tone as "
            "a single number between 0.0 (very positive) and 1.0 (very "
            "negative/distressed). Do NOT diagnose. Respond ONLY as JSON of the "
            'form {"negative_sentiment": <float>}.\n\nEntry:\n' + text
        )
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = json.loads(resp.text)
        val = float(data["negative_sentiment"])
        return max(0.0, min(1.0, val))
    except Exception:
        # Any error (no package, bad key, network, parse) -> deterministic mode.
        return None


def gemini_reflection(text: str) -> str | None:
    """Generate a gentle, non-clinical 1-2 sentence reflection for an entry.

    Guardrailed: supportive, never diagnostic, never alarming. Returns None if
    Gemini is disabled or anything fails (the UI then simply shows nothing).
    """
    if not settings.gemini_enabled or not text.strip():
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = (
            "You are a warm, supportive journaling companion. In 1-2 short "
            "sentences, gently reflect back what the writer might be "
            "experiencing and offer one small, kind suggestion (rest, a walk, "
            "reaching out to someone). Rules: do NOT diagnose, do NOT use "
            "clinical terms, do NOT be alarming, do NOT give medical advice. "
            "Be brief and human.\n\nJournal entry:\n" + text
        )
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.6),
        )
        out = (resp.text or "").strip()
        return out or None
    except Exception:
        return None


def extract_features(text: str, *, with_reflection: bool = True) -> dict:
    """Full feature vector: deterministic counts + (optional) Gemini sentiment.

    If Gemini is enabled and ``with_reflection`` is True, also attaches a gentle
    non-clinical ``reflection`` string.
    """
    feats = extract_deterministic(text)
    gem = _gemini_sentiment(text)
    if gem is not None:
        feats["neg_sentiment"] = round(gem, 4)
        feats["sentiment_source"] = "gemini"
    if with_reflection:
        refl = gemini_reflection(text)
        if refl:
            feats["reflection"] = refl
    return feats
