"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date as date_cls

from pydantic import BaseModel, Field


class EntryIn(BaseModel):
    date: date_cls | None = Field(
        default=None, description="ISO date; defaults to today if omitted."
    )
    journal_text: str = Field(default="", max_length=20_000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    social_count: int | None = Field(
        default=None, ge=0, le=200,
        description="Meaningful social interactions that day.",
    )
    energy: int | None = Field(
        default=None, ge=1, le=5, description="Self-reported energy 1..5."
    )
    # --- Passive signals (optional; from wearables / phone) -----------------
    steps: int | None = Field(
        default=None, ge=0, le=100_000,
        description="Daily step count (e.g. from Google Fit).",
    )
    active_minutes: int | None = Field(
        default=None, ge=0, le=1440,
        description="Active/move minutes (e.g. from Google Fit).",
    )
    screen_time_min: int | None = Field(
        default=None, ge=0, le=1440,
        description="Total phone screen-time minutes (passive phone signal).",
    )


class SeedIn(BaseModel):
    scenario: str = Field(
        default="decline",
        description="'decline' (stable then gradual drift), 'recurring' (two "
                    "episodes, for relapse fingerprinting), or 'stable'.",
    )
    days: int = Field(default=60, ge=14, le=180)


class InterventionTryIn(BaseModel):
    key: str = Field(description="Intervention signal key being tried now.")


class AssessmentIn(BaseModel):
    date: date_cls | None = None
    instrument: str = Field(description="'PHQ-9' or 'GAD-7'.")
    responses: list[int] | None = Field(
        default=None, description="Per-item scores (0..3). Preferred."
    )
    total: int | None = Field(
        default=None, ge=0, le=27,
        description="Precomputed total (used if responses omitted).",
    )


class ContactIn(BaseModel):
    """A trusted contact in the user's opt-in Circle of Care."""
    name: str = Field(min_length=1, max_length=120)
    method: str = Field(
        default="other",
        description="How to reach them: 'phone', 'email', 'text', 'other'.",
    )
    detail: str = Field(
        default="", max_length=200,
        description="Phone number, email, or note (stored locally only).",
    )
    notify_tier: int = Field(
        default=3, ge=2, le=3,
        description="Minimum tier at which to suggest nudging this contact.",
    )


class FitSyncIn(BaseModel):
    """Request to (simulate) syncing passive data from Google Fit."""
    days: int = Field(default=60, ge=1, le=180)
    # In a real integration this would carry an OAuth access token. For the
    # demo we simulate realistic wearable data aligned to existing entries.
    access_token: str | None = None


class BigQuerySyncIn(BaseModel):
    consent: bool = Field(
        default=False,
        description="Explicit confirmation for this de-identified export.",
    )


class SignalContribution(BaseModel):
    key: str
    label: str
    contribution: float
    message: str


class Intervention(BaseModel):
    key: str
    title: str
    action: str
    duration: str
    rationale: str


class StatusOut(BaseModel):
    has_data: bool
    calibrating: bool
    aura_index: float | None
    tier: int | None
    tier_label: str | None
    tier_message: str | None
    safety_alert: bool
    top_signals: list[SignalContribution]
    latest_date: str | None
    entry_count: int
    reflection: str | None = None
    interventions: list[dict] = []
    proven_intervention: dict | None = None
    forecast: dict | None = None
    circle_nudge: dict | None = None
    engagement: dict | None = None
