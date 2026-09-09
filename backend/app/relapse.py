"""Relapse fingerprinting -- temporal pattern matching against personal history.

People who have declined before often don't recognise they're re-entering the
*same* pattern until it's severe again (hindsight bias -- we only see "this
feels like March" afterwards). This module compares the *shape* of the recent
signal window to the shape of previously-flagged decline episodes using Dynamic
Time Warping (DTW), which tolerates episodes that unfold at different speeds.

This is not thresholding or sentiment -- it's temporal self-comparison, the
deepest expression of Aura's "baseline-relative" philosophy: your best
reference for what's happening now is what already happened to *you*.

Pure standard library (no numpy) to stay dependency-free and offline-capable.
"""
from __future__ import annotations

from datetime import date

# Core signals whose per-day contributions define the episode "shape".
_VECTOR_KEYS = ["sleep_hours", "social_count", "energy", "neg_sentiment"]

CURRENT_WINDOW = 14        # days of recent history to fingerprint
MIN_EPISODE_LEN = 5        # a decline episode is at least this many days
EPISODE_TIER = 2           # tier >= this counts as "in an episode"
MERGE_GAP = 3              # merge episodes separated by <= this many days
SIMILARITY_THRESHOLD = 45  # report matches at/above this similarity (0-100)


def _vec(day: dict) -> list[float]:
    c = day.get("contributions", {})
    return [float(c.get(k, 0.0)) for k in _VECTOR_KEYS]


def _normalize(seq: list[list[float]]) -> list[list[float]]:
    """Per-dimension min-max normalise a sequence to [0,1] so DTW compares the
    *shape* of a decline, not its absolute magnitude (a mild and a severe
    episode with the same trajectory should look alike)."""
    if not seq:
        return seq
    dims = len(seq[0])
    mins = [min(row[d] for row in seq) for d in range(dims)]
    maxs = [max(row[d] for row in seq) for d in range(dims)]
    spans = [(maxs[d] - mins[d]) or 1.0 for d in range(dims)]
    return [[(row[d] - mins[d]) / spans[d] for d in range(dims)] for row in seq]


def _dist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def dtw_distance(seq_a: list[list[float]], seq_b: list[list[float]]) -> float:
    """Dynamic Time Warping distance between two multivariate sequences."""
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0:
        return float("inf")
    INF = float("inf")
    prev = [INF] * (m + 1)
    prev[0] = 0.0
    # Standard DTW with a rolling row to keep memory small.
    for i in range(1, n + 1):
        cur = [INF] * (m + 1)
        # cur[0] stays INF for i>=1 (can't match empty b)
        for j in range(1, m + 1):
            cost = _dist(seq_a[i - 1], seq_b[j - 1])
            cur[j] = cost + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return prev[m]


def _similarity(distance: float, length: int) -> float:
    """Length-normalised distance -> 0..100 similarity (higher = more alike).

    On min-max normalised sequences the per-step distance is bounded in
    [0, 2], so distance/length lands in roughly [0, 2]; scale that to 0..100.
    """
    if length <= 0:
        return 0.0
    norm = distance / length
    return round(max(0.0, 100.0 - norm * 55.0), 1)


def extract_episodes(timeline: list[dict]) -> list[dict]:
    """Find contiguous decline episodes (tier >= EPISODE_TIER, merged)."""
    scored = [d for d in timeline if not d.get("calibrating")]
    runs: list[list[dict]] = []
    cur: list[dict] = []
    gap = 0
    for d in scored:
        if d.get("tier", 0) >= EPISODE_TIER:
            if cur and gap > MERGE_GAP:
                runs.append(cur)
                cur = []
            cur.append(d)
            gap = 0
        else:
            if cur:
                gap += 1
                if gap > MERGE_GAP:
                    runs.append(cur)
                    cur = []
    if cur:
        runs.append(cur)

    episodes = []
    for run in runs:
        if len(run) >= MIN_EPISODE_LEN:
            episodes.append({
                "start": run[0]["date"],
                "end": run[-1]["date"],
                "days": run,
                "peak_index": max(d.get("aura_index", 0) for d in run),
            })
    return episodes


def find_similar_past_episodes(timeline: list[dict], *,
                               window: int = CURRENT_WINDOW) -> dict:
    """Fingerprint the recent window against past episodes via DTW."""
    scored = [d for d in timeline if not d.get("calibrating")]
    if len(scored) < window + MIN_EPISODE_LEN:
        return {"available": False,
                "reason": "Not enough history yet to compare patterns."}

    current = scored[-window:]
    current_start = current[0]["date"]
    current_vec = _normalize([_vec(d) for d in current])

    episodes = extract_episodes(timeline)
    # Only compare against episodes that ended before the current window began.
    past = [e for e in episodes if e["end"] < current_start]
    if not past:
        return {"available": True, "matches": [],
                "current_range": [current_start, current[-1]["date"]],
                "note": "No prior decline episodes to compare against yet."}

    matches = []
    for ep in past:
        ep_vec = _normalize([_vec(d) for d in ep["days"]])
        dist = dtw_distance(current_vec, ep_vec)
        sim = _similarity(dist, max(len(current_vec), len(ep_vec)))
        if sim >= SIMILARITY_THRESHOLD:
            matches.append({
                "start": ep["start"],
                "end": ep["end"],
                "similarity": sim,
                "peak_index": round(ep["peak_index"], 1),
            })
    matches.sort(key=lambda m: -m["similarity"])
    return {
        "available": True,
        "current_range": [current_start, current[-1]["date"]],
        "matches": matches,
    }
