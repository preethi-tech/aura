# Aura — a privacy-first mental-health early-warning companion

Aura is a small, self-hostable web app that helps a person notice **sustained
changes in their own behavioral signals** (sleep, social contact, energy,
journal tone, self-focus, absolutist language) and connects them to support
**earlier**. It is built around three ideas that most demo projects skip:
**personalized baselines**, **trend-based (not single-point) detection**, and
**explainability** — with a safety layer that never depends on the model.

> **Aura is not a medical device.** It does not diagnose, treat, or predict any
> condition. It is a self-awareness tool. It never contacts anyone on your
> behalf; a human is always in the loop.

---

## Why it's interesting (the parts that stand out)

- **Personalized baselines** — every signal is normalized against the user's
  *own* recent history (robust median / MAD), not a population norm. "Withdrawn"
  for an introvert differs from an extrovert.
- **Trend, not single points** — only *concerning* deviations are counted and
  then smoothed over a window, so one rough day never raises an alert; only
  **sustained, multi-signal drift** does.
- **Signal fusion** — seven weak signals (sleep, social contact, energy, journal
  tone, self-focus, absolutist language, future orientation) are fused into a
  single 0–100 **Aura Index** with transparent weights.
- **Explainability** — every reading decomposes into per-signal contributions
  ("*why* is it elevated"). No black box.
- **Validated ground truth + evaluation** — built-in **PHQ-9 / GAD-7**
  questionnaires and an evaluation harness that reports correlation, **lead
  time**, and precision/recall of the passive index vs the questionnaires.
- **Safety is not gated behind ML** — explicit crisis language *immediately*
  surfaces crisis resources, independent of the trend score.
- **Privacy by construction** — 100% local storage (a single SQLite file), no
  Firebase, no accounts, one-click "delete all my data". Gemini is *optional*.

---

## Architecture

```
frontend/ (static HTML + CSS + Chart.js)  ──►  FastAPI (single process)
                                                │
                                                ├─ features.py   linguistic feature extraction
                                                │                 (deterministic; optional Gemini)
                                                ├─ analysis.py   personalized baselines +
                                                │                 trend fusion → Aura Index + tiers
                                                ├─ safety.py     crisis-language detection + resources
                                                └─ db.py         local SQLite (no cloud)
```

The engine has **two layers of feature extraction**:

1. **Deterministic / offline (always on):** first-person-singular pronoun ratio,
   absolutist-word ratio (Al-Mosaiwi & Johnson-Laird, 2018), social-reference
   ratio, and a lexicon sentiment estimate. Transparent and reproducible.
2. **Gemini enrichment (optional):** if `GEMINI_API_KEY` is set, Gemini refines
   the negative-sentiment score. The objective *counts* always stay
   deterministic, so the app is fully functional and explainable offline.

### How signals become the Aura Index

For each signal and day: compute a **personal z-score** against a trailing
baseline window → keep only the *concerning* direction → weight → sum →
**smooth over a rolling window** (enforces "sustained") → squash to **0–100**.
Tiers: `0 Stable · 1 Notice · 2 Connect · 3 Reach out now`. Tunables live at the
top of `backend/app/analysis.py`.

---

## Quick start

**Prerequisites:** Python 3.10+ (tested on 3.12).

### Windows (PowerShell)
```powershell
.\run.ps1
```

### macOS / Linux
```bash
./run.sh
```

Then open <http://127.0.0.1:8000> and click **"Load 60-day demo"** to see a
healthy baseline drift into a sustained decline that the engine flags through
the tiers.

### Manual run
```bash
cd backend
python -m venv .venv && . .venv/bin/activate      # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Enable Gemini (optional)
```bash
cp backend/.env.example backend/.env
# put your Google AI Studio key in GEMINI_API_KEY
```

---

## API

| Method | Path            | Description                                        |
| ------ | --------------- | -------------------------------------------------- |
| GET    | `/api/health`   | Status + whether Gemini is enabled                 |
| GET    | `/api/status`   | Latest Aura Index, tier, "why", safety flag        |
| GET    | `/api/timeline` | Full per-day analysis series (for charts)          |
| GET    | `/api/entries`  | Raw stored check-ins                               |
| POST   | `/api/entries`  | Add/replace a daily check-in                       |
| POST   | `/api/seed`     | Generate a synthetic demo timeline                 |
| DELETE | `/api/data`     | Delete all locally stored data                     |
| GET    | `/api/resources`| Crisis resources                                   |
| GET    | `/api/assessments/schema` | PHQ-9 / GAD-7 items + response options    |
| GET    | `/api/assessments` | Stored assessment scores                        |
| POST   | `/api/assessments` | Submit a PHQ-9 / GAD-7 (item responses or total) |
| GET    | `/api/eval`     | Evaluation metrics (index vs PHQ-9/GAD-7)          |

Example:
```bash
curl -X POST localhost:8000/api/entries -H "Content-Type: application/json" \
  -d '{"journal_text":"I feel exhausted and alone, nothing ever changes.","sleep_hours":4,"social_count":0,"energy":1}'
```

---

## Evaluation & ground truth

Aura tracks two validated instruments — **PHQ-9** (depression) and **GAD-7**
(anxiety) — as ground truth. The harness (`backend/app/evaluation.py`,
`GET /api/eval`) reports:

- **correlation** — Pearson r between the passive Aura Index and each instrument
- **lead time** — days the index crossed the "connect" tier *before* the first
  PHQ-9 case (positive = earlier warning)
- **precision / recall / F1** — day-level, tier ≥ 2 as a positive prediction

On the synthetic demo you'll see roughly: PHQ-9 r ≈ 0.76, GAD-7 r ≈ 0.78,
**lead time ≈ 15 days**, recall = 1.0. These are **illustrative on synthetic
data** — real validity needs an IRB study (see `docs/MODEL_CARD.md`).

Run the harness from the CLI:

```bash
cd backend && python -m app.evaluation   # prints metrics for the stored user
```

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q                 # 40 tests: features, safety, engine,
                                          # assessments, evaluation, API
```

## Docs

- `docs/SCIENTIFIC_GROUNDING.md` — digital-phenotyping evidence per signal
- `docs/MODEL_CARD.md` — intended use, out-of-scope, metrics, ethics
- `docs/DATA_CARD.md` — what is collected/derived/stored and sent to Gemini
- `docs/DEPLOY.md` — Docker + Cloud Run steps

---

## Deploying (no Firebase)

It's a single ASGI app + a SQLite file, so it runs anywhere. Full steps
(local Docker + Cloud Run + persistence caveats) are in **`docs/DEPLOY.md`**.

```bash
docker build -t aura:local . && docker run --rm -p 8080:8080 aura:local
# or straight to Cloud Run:
gcloud run deploy aura --source . --allow-unauthenticated --port 8080
```

Note: SQLite on Cloud Run is per-instance/ephemeral — fine for a demo; use a
GCS volume or Cloud SQL for real persistence (see `docs/DEPLOY.md`).

---

## Responsible-AI notes (read before extending)

- **Positioning matters.** Keep it a *wellness / self-awareness* tool. Do not
  add diagnostic or predictive claims — that changes the regulatory picture
  (FDA SaMD) and the ethics.
- **False positives cause harm** (anxiety, alert fatigue). The upper tiers are
  intentionally conservative (require sustained multi-signal drift).
- **Bias.** Lexicon/LLM signals underperform on dialects, non-native speakers,
  and cultures that express distress differently. Any real deployment needs
  subgroup evaluation.
- **Human in the loop, always.** Aura surfaces resources; it never acts.

---

## Roadmap (how this maps to a larger GCP design)

Done in this build: future-orientation signal, PHQ-9/GAD-7 ground truth +
evaluation harness, model/data cards, optional Gemini reflection. Next:

- On-device feature extraction (Gemini Nano) so raw journals never leave the
  device; upload only differentially-private feature vectors.
- Voice-note prosody + passive sleep/social/mobility signals (with opt-in).
- BigQuery + `ARIMA_PLUS` for longitudinal, seasonality-aware anomaly detection.
- Vertex AI for a calibrated (trained) risk-fusion model, versioned in the
  Model Registry.

---

## Project layout

```
aura/
  backend/
    app/
      config.py       settings (env)
      db.py           SQLite persistence (entries + assessments)
      schemas.py      pydantic models
      features.py     deterministic + Gemini feature extraction, reflection
      analysis.py     baselines, trend fusion, tiers, explanations
      safety.py       crisis detection + resources
      assessments.py  PHQ-9 / GAD-7 scoring
      evaluation.py   correlation, lead time, precision/recall (+ CLI)
      seed.py         synthetic demo generator (+ ground-truth scores)
      main.py         FastAPI app + static hosting
    tests/            pytest suite (40 tests)
    requirements.txt · requirements-dev.txt · .env.example
  frontend/
    index.html · styles.css · app.js
  docs/
    SCIENTIFIC_GROUNDING.md · MODEL_CARD.md · DATA_CARD.md · DEPLOY.md
  Dockerfile · .dockerignore · run.ps1 · run.sh
```
