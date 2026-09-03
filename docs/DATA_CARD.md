# Data Card — Aura

Describes the data Aura collects, derives, stores, and (optionally) sends to
Gemini. Aura is local-first: there is no cloud account and no third-party
analytics.

## Data collected (all user-entered, opt-in)
| Field | Type | Source | Purpose |
| --- | --- | --- | --- |
| `journal_text` | free text | user | derive linguistic features; (optional) Gemini sentiment + reflection |
| `sleep_hours` | number | user | sleep signal |
| `social_count` | integer | user | social-contact signal |
| `energy` | 1–5 | user | energy signal |
| PHQ-9 / GAD-7 responses | 0–3 per item | user | validated ground-truth score |

## Data derived (stored)
- Linguistic features: `first_person_ratio`, `absolutist_ratio`,
  `future_focus_ratio`, `social_ratio`, `neg_sentiment`, `word_count`.
- `safety_flag` (boolean) — whether explicit crisis language was detected.
- Assessment `total` and `severity` band.
- The Aura Index and tiers are **computed on the fly**, not stored.

## Storage
- Single local **SQLite** file (default `backend/aura.db`). No external
  database, no Firebase, no accounts.
- Tables: `entries` (one row per day), `assessments` (one row per day per
  instrument).

## Data sent off-device
- **Only if `GEMINI_API_KEY` is set.** In that case the raw `journal_text` of a
  *new* entry is sent to the Google Gemini API to (a) estimate negative
  sentiment and (b) generate a gentle reflection. Demo seeding never calls
  Gemini. With no key, nothing leaves the machine.
- Deterministic features and all analysis run locally regardless.

## Retention & deletion
- Data persists in the local file until deleted.
- **`DELETE /api/data`** (and the "Delete all my data" button) removes all
  entries and assessments for the user immediately.

## Sensitivity & risk
- Journal text is highly sensitive. Mitigations in this build: local-only
  storage by default, no third-party analytics, one-click deletion, and Gemini
  being strictly optional. Not yet implemented (see roadmap): encryption at
  rest, on-device-only feature extraction, differential privacy, PII redaction
  before any cloud call.

## Provenance of demo data
- The demo timeline and its PHQ-9/GAD-7 scores are **synthetic and
  reproducible** (`backend/app/seed.py`, fixed RNG seed). No real personal data
  is included in this repository.
