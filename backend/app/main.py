"""FastAPI application: REST API + static frontend hosting.

Supports both SQLite (local) and Firestore (cloud) backends, Firebase
Authentication, Gemini AI, and Google Cloud Logging.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date as date_cls

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import engagement as engagement_mod
from .analysis import compute_timeline
from .assessments import INSTRUMENTS, RESPONSE_OPTIONS, score
from .auth import get_current_user
from .circle import build_nudge
from .cloud_logging import logger, setup_logging
from .config import settings
from .environment import correlate as correlate_daylight
from .evaluation import evaluate_stored
from .features import extract_deterministic, extract_features
from .insights import build_insights, forecast
from .interventions import best_proven, suggest
from .passive import sync_passive
from .relapse import find_similar_past_episodes
from .safety import CRISIS_RESOURCES, detect_crisis
from .schemas import (
    AssessmentIn, ContactIn, EntryIn, FitSyncIn, InterventionTryIn, SeedIn,
    StatusOut,
)
from . import seed as seed_module

# Dynamic DB backend selection
if settings.firestore_enabled:
    from .firebase_db import (
        add_contact, delete_all, delete_contact, get_assessments, get_contacts,
        get_entries, get_intervention_history, init_db, log_intervention,
        resolve_pending_interventions, update_passive, upsert_assessment,
        upsert_entry,
    )
else:
    from .db import (
        add_contact, delete_all, delete_contact, get_assessments, get_contacts,
        get_entries, get_intervention_history, init_db, log_intervention,
        resolve_pending_interventions, update_passive, upsert_assessment,
        upsert_entry,
    )

api = APIRouter(prefix="/api")


def _status_payload(user_id: str) -> dict:
    entries = get_entries(user_id)
    result = compute_timeline(entries)
    summary = result["summary"]
    timeline = result["timeline"]

    tier = summary.get("tier") or 0
    history = get_intervention_history(user_id)
    summary["interventions"] = suggest(
        tier, summary.get("top_signals", []), history=history)
    summary["proven_intervention"] = best_proven(history)
    summary["forecast"] = forecast(timeline)
    summary["engagement"] = engagement_mod.compute(entries)

    # Circle of Care nudge is opt-in and only relevant at higher tiers.
    if tier >= 2:
        summary["circle_nudge"] = build_nudge(tier, get_contacts(user_id))
    else:
        summary["circle_nudge"] = None
    return summary


def _current_index(user_id: str) -> float | None:
    entries = get_entries(user_id)
    return compute_timeline(entries)["summary"].get("aura_index")


@api.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "gemini_enabled": settings.gemini_enabled,
        "model": settings.GEMINI_MODEL if settings.gemini_enabled else None,
        "storage": "firestore" if settings.firestore_enabled else "sqlite",
        "firebase_auth": settings.firestore_enabled,
        "cloud_logging": settings.CLOUD_LOGGING_ENABLED,
    }


@api.get("/status", response_model=StatusOut)
def status(user_id: str = Depends(get_current_user)) -> dict:
    return _status_payload(user_id)


@api.get("/timeline")
def timeline(user_id: str = Depends(get_current_user)) -> dict:
    entries = get_entries(user_id)
    return compute_timeline(entries)


@api.get("/entries")
def list_entries(user_id: str = Depends(get_current_user)) -> dict:
    entries = get_entries(user_id)
    return {"entries": entries, "count": len(entries)}


@api.post("/entries", response_model=StatusOut)
def create_entry(payload: EntryIn,
                 user_id: str = Depends(get_current_user)) -> dict:
    d = (payload.date or date_cls.today()).isoformat()
    text = payload.journal_text or ""
    feats = extract_features(text)
    safety = detect_crisis(text)
    logger.info(f"Entry created for user={user_id} date={d}")
    upsert_entry(
        user_id=user_id,
        date=d,
        journal_text=text,
        sleep_hours=payload.sleep_hours,
        social_count=payload.social_count,
        energy=payload.energy,
        features=feats,
        safety_flag=safety,
        steps=payload.steps,
        active_minutes=payload.active_minutes,
        screen_time_min=payload.screen_time_min,
    )
    # Close the loop on any recently-tried micro-intervention (Feature 3):
    # this new check-in's index is the "after" measurement.
    idx = _current_index(user_id)
    if idx is not None:
        resolve_pending_interventions(user_id, idx)
    return _status_payload(user_id)


@api.post("/seed", response_model=StatusOut)
def seed(payload: SeedIn,
         user_id: str = Depends(get_current_user)) -> dict:
    delete_all(user_id)
    for e in seed_module.generate(scenario=payload.scenario, days=payload.days):
        feats = extract_deterministic(e["journal_text"])
        upsert_entry(
            user_id=user_id,
            date=e["date"],
            journal_text=e["journal_text"],
            sleep_hours=e["sleep_hours"],
            social_count=e["social_count"],
            energy=e["energy"],
            features=feats,
            safety_flag=detect_crisis(e["journal_text"]),
            steps=e.get("steps"),
            active_minutes=e.get("active_minutes"),
            screen_time_min=e.get("screen_time_min"),
        )
    for a in seed_module.generate_assessments(
        scenario=payload.scenario, days=payload.days
    ):
        sc = score(a["instrument"], total=a["total"])
        upsert_assessment(
            user_id=user_id,
            date=a["date"],
            instrument=a["instrument"],
            total=sc["total"],
            severity=sc["severity"],
            responses=None,
        )
    # Seed a plausible intervention-effectiveness history (Feature 3) so the
    # "what works for you" panel is populated in the demo.
    for iv in seed_module.generate_interventions(
        scenario=payload.scenario, days=payload.days
    ):
        log_intervention(
            user_id=user_id,
            date=iv["date"],
            intervention_key=iv["intervention_key"],
            index_before=iv["index_before"],
            index_after=iv["index_after"],
        )
    logger.info(f"Demo seeded for user={user_id}")
    return _status_payload(user_id)


@api.delete("/data")
def wipe(user_id: str = Depends(get_current_user)) -> dict:
    n = delete_all(user_id)
    logger.info(f"Data wiped for user={user_id} count={n}")
    return {"deleted": n}


@api.get("/resources")
def resources() -> dict:
    return {"crisis_resources": CRISIS_RESOURCES}


@api.get("/assessments/schema")
def assessments_schema() -> dict:
    return {
        "response_options": [
            {"value": v, "label": lbl} for v, lbl in RESPONSE_OPTIONS
        ],
        "instruments": {
            name: {"items": meta["items"], "max": meta["max"],
                   "case_threshold": meta["case_threshold"]}
            for name, meta in INSTRUMENTS.items()
        },
    }


@api.get("/assessments")
def list_assessments(user_id: str = Depends(get_current_user)) -> dict:
    return {"assessments": get_assessments(user_id)}


@api.post("/assessments")
def create_assessment(payload: AssessmentIn,
                      user_id: str = Depends(get_current_user)) -> dict:
    d = (payload.date or date_cls.today()).isoformat()
    sc = score(payload.instrument, responses=payload.responses,
               total=payload.total)
    upsert_assessment(
        user_id=user_id,
        date=d,
        instrument=sc["instrument"],
        total=sc["total"],
        severity=sc["severity"],
        responses=payload.responses,
    )
    return {**sc, "date": d, "safety_alert": sc.get("item9_flag", False)}


@api.get("/eval")
def eval_report(user_id: str = Depends(get_current_user)) -> dict:
    return evaluate_stored(user_id)


@api.get("/insights")
def insights(user_id: str = Depends(get_current_user)) -> dict:
    """Explainable AI: weekly summary, recurring cycles, and trend forecast."""
    entries = get_entries(user_id)
    timeline = compute_timeline(entries)["timeline"]
    out = build_insights(timeline)
    out["engagement"] = engagement_mod.compute(entries)
    return out


@api.get("/engagement")
def engagement(user_id: str = Depends(get_current_user)) -> dict:
    """Writing-withdrawal detection: are entries getting shorter / less often?"""
    return engagement_mod.compute(get_entries(user_id))


@api.get("/relapse")
def relapse(user_id: str = Depends(get_current_user)) -> dict:
    """Relapse fingerprinting: DTW similarity of the recent window to past
    decline episodes, enriched with what helped during those episodes."""
    entries = get_entries(user_id)
    timeline = compute_timeline(entries)["timeline"]
    result = find_similar_past_episodes(timeline)
    # Enrich each match with the most effective intervention tried around then.
    history = get_intervention_history(user_id)
    for m in result.get("matches", []):
        m["what_helped"] = _what_helped(history, m["start"], m["end"])
    return result


def _what_helped(history: list[dict], start: str, end: str) -> dict | None:
    """Most effective intervention logged within/after an episode window."""
    from .interventions import _LIBRARY
    best = None
    for row in history:
        d = row.get("date", "")
        delta = row.get("delta")
        if delta is None or d < start:
            continue
        key = row.get("intervention_key")
        if key not in _LIBRARY:
            continue
        if best is None or delta < best[1]:
            best = (key, delta)
    if best and best[1] <= -1:
        key = best[0]
        return {"key": key, "title": _LIBRARY[key]["title"],
                "action": _LIBRARY[key]["action"],
                "avg_effect": round(best[1], 1)}
    return None


@api.post("/interventions/try")
def try_intervention(payload: InterventionTryIn,
                     user_id: str = Depends(get_current_user)) -> dict:
    """Record that the user is trying an intervention now. The NEXT check-in's
    Aura Index becomes the 'after' measurement (Feature 3 effectiveness loop)."""
    idx = _current_index(user_id)
    log_intervention(
        user_id=user_id,
        date=date_cls.today().isoformat(),
        intervention_key=payload.key,
        index_before=idx,
    )
    logger.info(f"Intervention tried user={user_id} key={payload.key}")
    return {"logged": True, "key": payload.key, "index_before": idx,
            "note": "Nice. Your next check-in will measure whether it helped."}


@api.get("/environment")
def environment(lat: float | None = None, lon: float | None = None,
                user_id: str = Depends(get_current_user)) -> dict:
    """Seasonal context: correlate the Aura Index with local daylight hours."""
    entries = get_entries(user_id)
    timeline = compute_timeline(entries)["timeline"]
    return correlate_daylight(timeline, lat=lat, lon=lon)


@api.post("/fit/sync")
def fit_sync(payload: FitSyncIn,
             user_id: str = Depends(get_current_user)) -> dict:
    """Pull passive signals (steps/active minutes/screen time) from Google Fit.

    Falls back to a realistic simulation when no live OAuth token is provided
    so the passive pipeline is always demoable. Only updates days that already
    have a check-in (passive data augments, never fabricates, entries).
    """
    entries = get_entries(user_id)
    if not entries:
        return {"synced": 0, "source": "none",
                "detail": "Add or seed check-ins first, then sync passive data."}
    rows, source = sync_passive(
        entries, days=payload.days, access_token=payload.access_token)
    synced = 0
    for r in rows:
        ok = update_passive(
            user_id=user_id,
            date=r["date"],
            steps=r.get("steps"),
            active_minutes=r.get("active_minutes"),
            screen_time_min=r.get("screen_time_min"),
            sleep_hours=r.get("sleep_hours"),
        )
        synced += 1 if ok else 0
    logger.info(f"Passive sync user={user_id} source={source} count={synced}")
    return {"synced": synced, "source": source, **_status_payload(user_id)}


@api.get("/contacts")
def list_contacts(user_id: str = Depends(get_current_user)) -> dict:
    return {"contacts": get_contacts(user_id)}


@api.post("/contacts")
def create_contact(payload: ContactIn,
                   user_id: str = Depends(get_current_user)) -> dict:
    c = add_contact(
        user_id=user_id, name=payload.name, method=payload.method,
        detail=payload.detail, notify_tier=payload.notify_tier,
    )
    logger.info(f"Contact added user={user_id}")
    return c


@api.delete("/contacts/{contact_id}")
def remove_contact(contact_id: str,
                   user_id: str = Depends(get_current_user)) -> dict:
    # SQLite uses int ids; Firestore uses string ids. Accept both.
    cid: object = contact_id
    if not settings.firestore_enabled:
        try:
            cid = int(contact_id)
        except ValueError:
            cid = -1
    n = delete_contact(user_id, cid)
    return {"deleted": n}


@api.get("/export")
def export_data(user_id: str = Depends(get_current_user)) -> dict:
    """Privacy-first data export: the user can download everything we hold."""
    return {
        "version": __version__,
        "user_id": user_id,
        "entries": get_entries(user_id),
        "assessments": get_assessments(user_id),
        "contacts": get_contacts(user_id),
    }


@api.post("/auth/verify")
def verify_token(user_id: str = Depends(get_current_user)) -> dict:
    """Verify Firebase ID token and return user info."""
    return {"authenticated": True, "user_id": user_id}


@api.get("/firebase-config")
def firebase_config() -> dict:
    """Return Firebase config for frontend initialization."""
    if not settings.firestore_enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "config": {
            "apiKey": settings.FIREBASE_WEB_API_KEY,
            "authDomain": f"{settings.FIREBASE_PROJECT_ID}.firebaseapp.com",
            "projectId": settings.FIREBASE_PROJECT_ID,
            "storageBucket": f"{settings.FIREBASE_PROJECT_ID}.appspot.com",
        }
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    logger.info(f"Aura started: storage={('firestore' if settings.firestore_enabled else 'sqlite')}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Aura", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api)

    from .config import FRONTEND_DIR
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True),
                  name="frontend")
    else:
        @app.get("/")
        def _no_frontend() -> JSONResponse:
            return JSONResponse({"detail": "frontend not found"}, status_code=404)

    return app


app = create_app()
