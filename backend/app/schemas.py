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


class SeedIn(BaseModel):
    scenario: str = Field(
        default="decline",
        description="'decline' (stable then gradual drift) or 'stable'.",
    )
    days: int = Field(default=60, ge=14, le=180)


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


class SignalContribution(BaseModel):
    key: str
    label: str
    contribution: float
    message: str


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
