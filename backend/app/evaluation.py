"""Evaluation harness.

Compares the passive Aura Index against periodic PHQ-9 / GAD-7 self-reports
(ground truth) and reports:

  * correlation  -- Pearson r between Aura Index and each instrument
  * lead_time    -- days the Aura Index crossed the "connect" tier BEFORE the
                    first PHQ-9 case (>= 10). Positive == earlier warning.
  * precision/recall/F1 -- day-level, treating Aura tier >= 2 as a positive
                    prediction and nearest PHQ-9 >= 10 as the true label.

All metrics are ILLUSTRATIVE on synthetic/self-reported data. Real clinical
validation requires an IRB-approved prospective study (see MODEL_CARD.md).
"""
from __future__ import annotations

from datetime import date

# Tunables
MAX_GAP_DAYS = 21          # max distance to align an Aura day to an assessment
DETECT_INDEX = 50.0        # Aura Index that counts as a "positive" (tier 2)
PHQ_CASE = 10              # PHQ-9 >= 10 == moderate+ (common case threshold)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / ((sxx * syy) ** 0.5)


def _nearest(pairs: list[tuple[date, float]], target: date,
             max_gap: int) -> float | None:
    best, best_gap = None, None
    for d, v in pairs:
        g = abs((d - target).days)
        if g <= max_gap and (best_gap is None or g < best_gap):
            best, best_gap = v, g
    return best


def evaluate(timeline: list[dict], assessments: list[dict]) -> dict:
    aura = [
        (date.fromisoformat(d["date"]), float(d["aura_index"]))
        for d in timeline if d.get("aura_index") is not None
    ]
    result: dict = {
        "available": False,
        "n_entries": len(aura),
        "n_assessments": len(assessments),
        "params": {
            "detect_index": DETECT_INDEX,
            "phq_case_threshold": PHQ_CASE,
            "max_gap_days": MAX_GAP_DAYS,
        },
        "notes": "Illustrative metrics on synthetic/self-reported data.",
    }
    if not aura or not assessments:
        return result

    # --- correlation --------------------------------------------------------
    corr: dict[str, float | None] = {}
    for inst in ("PHQ-9", "GAD-7"):
        xs, ys = [], []
        for a in assessments:
            if a["instrument"] != inst:
                continue
            ai = _nearest(aura, date.fromisoformat(a["date"]), MAX_GAP_DAYS)
            if ai is not None:
                xs.append(ai)
                ys.append(float(a["total"]))
        r = _pearson(xs, ys)
        corr[inst] = round(r, 3) if r is not None else None
    result["correlation"] = corr

    # --- lead time ----------------------------------------------------------
    phq_cases = sorted(
        date.fromisoformat(a["date"])
        for a in assessments
        if a["instrument"] == "PHQ-9" and a["total"] >= PHQ_CASE
    )
    detections = sorted(d for d, idx in aura if idx >= DETECT_INDEX)
    onset = phq_cases[0] if phq_cases else None
    detection = detections[0] if detections else None
    result["clinical_onset"] = onset.isoformat() if onset else None
    result["detection_date"] = detection.isoformat() if detection else None
    result["lead_time_days"] = (
        (onset - detection).days if onset and detection else None
    )

    # --- precision / recall (day-level, PHQ-9) ------------------------------
    phq_pairs = [
        (date.fromisoformat(a["date"]), float(a["total"]))
        for a in assessments if a["instrument"] == "PHQ-9"
    ]
    tp = fp = fn = tn = 0
    for d, idx in aura:
        gt = _nearest(phq_pairs, d, MAX_GAP_DAYS)
        if gt is None:
            continue
        pred = idx >= DETECT_INDEX
        actual = gt >= PHQ_CASE
        if pred and actual:
            tp += 1
        elif pred and not actual:
            fp += 1
        elif not pred and actual:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall else None
    )
    result["confusion"] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
    result["precision"] = round(precision, 3) if precision is not None else None
    result["recall"] = round(recall, 3) if recall is not None else None
    result["f1"] = round(f1, 3) if f1 is not None else None
    result["available"] = True
    return result


def evaluate_stored(user_id: str | None = None) -> dict:
    """Load stored data for a user and evaluate (used by the API and CLI)."""
    from .analysis import compute_timeline
    from .config import settings

    if settings.firestore_enabled:
        from .firebase_db import get_assessments, get_entries
    else:
        from .db import get_assessments, get_entries

    uid = user_id or settings.DEFAULT_USER
    timeline = compute_timeline(get_entries(uid))["timeline"]
    return evaluate(timeline, get_assessments(uid))


if __name__ == "__main__":  # pragma: no cover - manual CLI
    import json

    from .db import init_db
    init_db()
    print(json.dumps(evaluate_stored(), indent=2))
