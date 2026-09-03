"""FastAPI application: REST API + static frontend hosting.

Supports both SQLite (local) and Firestore (cloud) backends, Firebase
Authentication, Gemini AI, and Google Cloud Logging.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date as date_cls

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .analysis import compute_timeline
from .assessments import INSTRUMENTS, RESPONSE_OPTIONS, score
from .auth import get_current_user
from .cloud_logging import logger, setup_logging
from .config import settings
from .evaluation import evaluate_stored
from .features import extract_deterministic, extract_features
from .safety import CRISIS_RESOURCES, detect_crisis
from .schemas import AssessmentIn, EntryIn, SeedIn, StatusOut
from . import seed as seed_module

# Dynamic DB backend selection
if settings.firestore_enabled:
    from .firebase_db import (
        delete_all, get_assessments, get_entries, init_db, upsert_assessment,
        upsert_entry,
    )
else:
    from .db import (
        delete_all, get_assessments, get_entries, init_db, upsert_assessment,
        upsert_entry,
    )

api = APIRouter(prefix="/api")


def _status_payload(user_id: str) -> dict:
    entries = get_entries(user_id)
    return compute_timeline(entries)["summary"]


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
    )
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


@api.post("/auth/verify")
def verify_token(user_id: str = Depends(get_current_user)) -> dict:
    """Verify Firebase ID token and return user info."""
    return {"authenticated": True, "user_id": user_id}


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
