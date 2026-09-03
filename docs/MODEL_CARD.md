# Model Card — Aura Index

Following the *Model Cards for Model Reporting* framework (Mitchell et al., 2019).

## Model details
- **Name:** Aura Index (v0.1.0)
- **Type:** Rule-based, interpretable multi-signal risk-fusion model — **not** a
  trained classifier. Per-signal personalized z-scores (robust median/MAD over a
  trailing window) → concerning-direction clamp → weighted sum → rolling-window
  smoothing → 0–100 index → 4 tiers. Optional Gemini call refines one input
  feature (negative sentiment) and produces a non-clinical reflection string.
- **Inputs:** self-reported sleep hours, social-contact count, energy (1–5); and
  journal-text-derived features (first-person ratio, absolutist ratio,
  future-focus ratio, negative sentiment).
- **Owner/contact:** project author (portfolio project).

## Intended use
- **Primary:** personal *self-awareness* — help an individual notice sustained
  changes in their own behavioral signals and reach support earlier.
- **Users:** the individual themselves (single-user local deployment).

## Out-of-scope / prohibited use
- **Not** for diagnosis, screening, triage, or prediction of any condition,
  including suicide risk.
- **Not** for use by clinicians, employers, insurers, or schools to make
  decisions about a person.
- **Not** a crisis-detection system. (Explicit crisis *language* surfaces
  resources via a separate deterministic safety layer — this is a safety net,
  not a predictive claim.)
- No autonomous action is ever taken on a user's behalf.

## Factors
- Language, dialect, and cultural expression of distress strongly affect the
  linguistic and lexicon features. Non-native speakers and non-Western idioms of
  distress are expected to be under-served.
- Baselines require history; the model deliberately does not score during an
  initial calibration window.
- Self-reported signals are subject to recall and reporting bias.

## Metrics
- The evaluation harness reports: Pearson correlation (Aura Index vs PHQ-9 and
  GAD-7), **lead time** to first PHQ-9 case, and day-level precision/recall/F1
  (tier ≥ 2 as positive; nearest PHQ-9 ≥ 10 as label). See
  `backend/app/evaluation.py` and `GET /api/eval`.
- **Reported numbers to date are ILLUSTRATIVE**, computed on synthetic demo data
  (`seed.py`). They demonstrate the pipeline, not clinical performance.

## Evaluation data
- Synthetic reproducible timeline (stable baseline → gradual multi-signal
  decline) with synthetic PHQ-9/GAD-7 ground truth. No human-subjects data.

## Ethical considerations
- **False positives** can cause anxiety and alert fatigue; upper tiers are tuned
  conservatively (require sustained, multi-signal drift).
- **False negatives** must not create false reassurance; the UI never claims
  safety and always exposes crisis resources.
- **Human-in-the-loop** by design: Aura surfaces information and resources; a
  person always decides and acts.

## Caveats & recommendations
- Real clinical validity requires an **IRB-approved prospective study** with
  consented participants, subgroup analysis, and comparison against clinician
  assessment — none of which this project claims.
- Before any real deployment: add authentication, per-user data isolation,
  encryption at rest, subgroup fairness evaluation, and a documented escalation
  protocol reviewed by a clinician.
