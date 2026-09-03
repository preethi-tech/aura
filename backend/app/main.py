"""FastAPI application: REST API + static frontend hosting.

Single process, single port. No external services required.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date as date_cls

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .analysis import compute_timeline
from .assessments import INSTRUMENTS, RESPONSE_OPTIONS, score
from .config import settings
from .db import (
    delete_all, get_assessments, get_entries, init_db, upsert_assessment,
    upsert_entry,
)
from .evaluation import evaluate_stored
from .features import extract_deterministic, extract_features
from .safety import CRISIS_RESOURCES, detect_crisis
from .schemas import AssessmentIn, EntryIn, SeedIn, StatusOut
from . import seed as seed_module

api = APIRouter(prefix="/api")


def _status_payload() -> dict:
    entries = get_entries(settings.DEFAULT_USER)
    return compute_timeline(entries)["summary"]


@api.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "gemini_enabled": settings.gemini_enabled,
        "model": settings.GEMINI_MODEL if settings.gemini_enabled else None,
    }


@api.get("/status", response_model=StatusOut)
def status() -> dict:
    return _status_payload()


@api.get("/timeline")
def timeline() -> dict:
    entries = get_entries(settings.DEFAULT_USER)
    return compute_timeline(entries)


@api.get("/entries")
def list_entries() -> dict:
    entries = get_entries(settings.DEFAULT_USER)
    # Do not leak raw journal text back by default beyond what the UI needs.
    return {"entries": entries, "count": len(entries)}


@api.post("/entries", response_model=StatusOut)
def create_entry(payload: EntryIn) -> dict:
    d = (payload.date or date_cls.today()).isoformat()
    text = payload.journal_text or ""
    feats = extract_features(text)
    safety = detect_crisis(text)
    upsert_entry(
        user_id=settings.DEFAULT_USER,
        date=d,
        journal_text=text,
        sleep_hours=payload.sleep_hours,
        social_count=payload.social_count,
        energy=payload.energy,
        features=feats,
        safety_flag=safety,
    )
    return _status_payload()


@api.post("/seed", response_model=StatusOut)
def seed(payload: SeedIn) -> dict:
    delete_all(settings.DEFAULT_USER)
    for e in seed_module.generate(scenario=payload.scenario, days=payload.days):
        # Deterministic features only for seeding -> fast and free (no LLM calls).
        feats = extract_deterministic(e["journal_text"])
        upsert_entry(
            user_id=settings.DEFAULT_USER,
            date=e["date"],
            journal_text=e["journal_text"],
            sleep_hours=e["sleep_hours"],
            social_count=e["social_count"],
            energy=e["energy"],
            features=feats,
            safety_flag=detect_crisis(e["journal_text"]),
        )
    # Seed matching PHQ-9 / GAD-7 ground truth for the evaluation harness.
    for a in seed_module.generate_assessments(
        scenario=payload.scenario, days=payload.days
    ):
        sc = score(a["instrument"], total=a["total"])
        upsert_assessment(
            user_id=settings.DEFAULT_USER,
            date=a["date"],
            instrument=a["instrument"],
            total=sc["total"],
            severity=sc["severity"],
            responses=None,
        )
    return _status_payload()


@api.delete("/data")
def wipe() -> dict:
    n = delete_all(settings.DEFAULT_USER)
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
def list_assessments() -> dict:
    return {"assessments": get_assessments(settings.DEFAULT_USER)}


@api.post("/assessments")
def create_assessment(payload: AssessmentIn) -> dict:
    d = (payload.date or date_cls.today()).isoformat()
    sc = score(payload.instrument, responses=payload.responses,
               total=payload.total)
    upsert_assessment(
        user_id=settings.DEFAULT_USER,
        date=d,
        instrument=sc["instrument"],
        total=sc["total"],
        severity=sc["severity"],
        responses=payload.responses,
    )
    # PHQ-9 self-harm item is a safety signal, surfaced independent of the model.
    return {**sc, "date": d, "safety_alert": sc.get("item9_flag", False)}


@api.get("/eval")
def eval_report() -> dict:
    return evaluate_stored(settings.DEFAULT_USER)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Aura", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # local single-user tool; tighten for deployment
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api)

    # Serve the static frontend at root (index.html for "/").
    from .config import FRONTEND_DIR
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True),
                  name="frontend")
    else:  # pragma: no cover - only if frontend missing
        @app.get("/")
        def _no_frontend() -> JSONResponse:
            return JSONResponse({"detail": "frontend not found"}, status_code=404)

    return app


app = create_app()
