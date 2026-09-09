"""Firestore persistence layer.

Mirrors the db.py interface so main.py can swap backends transparently.
Collections:
  users/{user_id}/entries/{date}      -- daily check-ins
  users/{user_id}/assessments/{date_instrument} -- PHQ-9 / GAD-7
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import settings

_db = None


def _get_db():
    """Lazy-init Firestore client."""
    global _db
    if _db is not None:
        return _db
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if settings.FIREBASE_CREDENTIALS:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
                firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})
            else:
                # On Cloud Run, uses Application Default Credentials
                firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})
        _db = firestore.client()
        return _db
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Firestore: {e}") from e


def init_db() -> None:
    """Verify Firestore connection (collections are created on first write)."""
    _get_db()


def upsert_entry(
    *,
    user_id: str,
    date: str,
    journal_text: str,
    sleep_hours: float | None,
    social_count: int | None,
    energy: int | None,
    features: dict,
    safety_flag: bool,
    steps: int | None = None,
    active_minutes: int | None = None,
    screen_time_min: int | None = None,
) -> None:
    db = _get_db()
    doc_ref = db.collection("users").document(user_id).collection("entries").document(date)
    doc_ref.set({
        "user_id": user_id,
        "date": date,
        "journal_text": journal_text,
        "sleep_hours": sleep_hours,
        "social_count": social_count,
        "energy": energy,
        "steps": steps,
        "active_minutes": active_minutes,
        "screen_time_min": screen_time_min,
        "features": features,
        "safety_flag": safety_flag,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, merge=True)


def update_passive(
    *,
    user_id: str,
    date: str,
    steps: int | None = None,
    active_minutes: int | None = None,
    screen_time_min: int | None = None,
    sleep_hours: float | None = None,
) -> bool:
    db = _get_db()
    doc_ref = db.collection("users").document(user_id).collection("entries").document(date)
    if not doc_ref.get().exists:
        return False
    payload = {k: v for k, v in {
        "steps": steps, "active_minutes": active_minutes,
        "screen_time_min": screen_time_min, "sleep_hours": sleep_hours,
    }.items() if v is not None}
    if payload:
        doc_ref.set(payload, merge=True)
    return True


def get_entries(user_id: str) -> list[dict]:
    db = _get_db()
    docs = (
        db.collection("users")
        .document(user_id)
        .collection("entries")
        .order_by("date")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def upsert_assessment(
    *,
    user_id: str,
    date: str,
    instrument: str,
    total: int,
    severity: str,
    responses: list[int] | None,
) -> None:
    db = _get_db()
    doc_id = f"{date}_{instrument}"
    doc_ref = db.collection("users").document(user_id).collection("assessments").document(doc_id)
    doc_ref.set({
        "user_id": user_id,
        "date": date,
        "instrument": instrument,
        "total": total,
        "severity": severity,
        "responses": responses or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def get_assessments(user_id: str) -> list[dict]:
    db = _get_db()
    docs = (
        db.collection("users")
        .document(user_id)
        .collection("assessments")
        .order_by("date")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


# --- Circle of Care contacts ------------------------------------------------
def add_contact(
    *, user_id: str, name: str, method: str, detail: str, notify_tier: int,
) -> dict:
    db = _get_db()
    coll = db.collection("users").document(user_id).collection("contacts")
    doc_ref = coll.document()
    data = {
        "id": doc_ref.id, "name": name, "method": method,
        "detail": detail, "notify_tier": int(notify_tier),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc_ref.set(data)
    return {"id": doc_ref.id, "name": name, "method": method,
            "detail": detail, "notify_tier": int(notify_tier)}


def get_contacts(user_id: str) -> list[dict]:
    db = _get_db()
    docs = (
        db.collection("users").document(user_id).collection("contacts").stream()
    )
    out = []
    for doc in docs:
        d = doc.to_dict()
        out.append({
            "id": doc.id, "name": d.get("name"), "method": d.get("method"),
            "detail": d.get("detail", ""), "notify_tier": d.get("notify_tier", 3),
        })
    return out


def delete_contact(user_id: str, contact_id) -> int:
    db = _get_db()
    doc_ref = (
        db.collection("users").document(user_id)
        .collection("contacts").document(str(contact_id))
    )
    if doc_ref.get().exists:
        doc_ref.delete()
        return 1
    return 0


# --- Intervention effectiveness log -----------------------------------------
def log_intervention(*, user_id: str, date: str, intervention_key: str,
                     index_before: float | None,
                     index_after: float | None = None) -> str:
    db = _get_db()
    coll = db.collection("users").document(user_id).collection("intervention_log")
    doc_ref = coll.document()
    delta = None
    if index_before is not None and index_after is not None:
        delta = index_after - index_before
    doc_ref.set({
        "date": date, "intervention_key": intervention_key,
        "index_before": index_before, "index_after": index_after,
        "delta": delta,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_ref.id


def resolve_pending_interventions(user_id: str, index_after: float) -> int:
    db = _get_db()
    coll = db.collection("users").document(user_id).collection("intervention_log")
    n = 0
    for doc in coll.stream():
        d = doc.to_dict()
        if d.get("index_after") is None and d.get("index_before") is not None:
            doc.reference.set({
                "index_after": index_after,
                "delta": index_after - d["index_before"],
            }, merge=True)
            n += 1
    return n


def get_intervention_history(user_id: str) -> list[dict]:
    db = _get_db()
    docs = (
        db.collection("users").document(user_id)
        .collection("intervention_log").stream()
    )
    rows = [doc.to_dict() for doc in docs]
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


def delete_all(user_id: str) -> int:
    db = _get_db()
    count = 0
    for coll_name in ("entries", "assessments", "contacts", "intervention_log"):
        docs = db.collection("users").document(user_id).collection(coll_name).stream()
        for doc in docs:
            doc.reference.delete()
            count += 1
    return count
