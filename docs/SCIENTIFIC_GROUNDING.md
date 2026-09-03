# Scientific grounding

Aura is built on **digital phenotyping** — the "moment-by-moment quantification
of the individual-level human phenotype in situ using data from personal digital
devices" (Onnela & Rauch, 2016; Torous et al., 2016). The premise: behavioral
and linguistic signals collected passively/self-reported can reflect changes in
mental state, and *sustained, multi-signal deviation from a person's own
baseline* is more informative than any single reading.

> Aura is a self-awareness tool, not a diagnostic or predictive medical device.
> The evidence below motivates the signals; it does not establish clinical
> validity for this implementation. See `MODEL_CARD.md`.

## Signal-by-signal evidence and implementation status

| Signal | Evidence (representative) | Direction | In Aura today |
| --- | --- | --- | --- |
| First-person singular pronouns (I, me, my) | Elevated self-focus associates with depression (Rude, Gortner & Pennebaker, 2004; Tackman et al., 2019) | ↑ concerning | ✅ `first_person_ratio` (deterministic) |
| Absolutist words (always, never, completely) | Elevated in anxiety/depression/suicidal-ideation forums (Al-Mosaiwi & Johnson-Laird, 2018) | ↑ concerning | ✅ `absolutist_ratio` (deterministic) |
| Reduced future orientation | Depression associates with reduced prospection / future-tense language | ↓ concerning | ✅ `future_focus_ratio` (deterministic) |
| Negative affect in language | Sentiment/affect lexicons & LLMs track mood (Pennebaker LIWC line of work; CLPsych shared tasks) | ↑ concerning | ✅ `neg_sentiment` (lexicon; optional Gemini refinement) |
| Voice acoustics (↓ pitch variability, ↓ speech rate, ↑ pauses, jitter/shimmer) | Prosodic markers of depression (Cummins et al., 2015; Mundt et al., 2007) | — | ❌ Not implemented (needs an audio pipeline — see Roadmap) |
| Sleep / circadian disruption | Both symptom and predictor of mood episodes; passively estimable from device usage timing | ↓ / irregular concerning | ⚠️ Self-reported `sleep_hours` proxy (no passive sensing yet) |
| Social withdrawal (↓ outgoing comms, ↓ mobility / radius of gyration) | Reduced sociality & mobility track depressive states (Saeb et al., 2015 — GPS/phone features vs PHQ-9) | ↓ concerning | ⚠️ Self-reported `social_count` proxy (no comms/GPS sensing yet) |
| Energy / anhedonia | Core depressive symptom (maps to PHQ-9 items) | ↓ concerning | ✅ Self-reported `energy` |

## Key modeling principle (implemented)

No single signal is diagnostic. Aura:

1. Normalizes each signal to the **user's own** trailing baseline (robust
   median / MAD) → a personal z-score.
2. Counts only **concerning-direction** deviations.
3. **Fuses** the weak signals with transparent weights.
4. **Smooths** over a rolling window so only *sustained* drift raises the index.
5. Withholds scoring during an initial calibration period (no baseline → no
   alert).

See `backend/app/analysis.py` (all tunables are at the top) and
`backend/app/features.py`.

## Ground truth & evaluation

Aura tracks two validated instruments as ground truth: **PHQ-9** (depression)
and **GAD-7** (anxiety), both with standard cut-points. The evaluation harness
(`backend/app/evaluation.py`) reports correlation, **lead time** (how much
earlier the Aura Index crosses the "connect" tier than the first PHQ-9 case),
and day-level precision/recall. On the synthetic demo these are illustrative
only.

## Roadmap to close the gaps honestly

- **Voice acoustics:** capture short voice notes → extract prosody
  (e.g., `praat-parselmouth`/`librosa`) server-side, or on-device.
- **Passive sleep/social/mobility:** on Android, derive sleep timing from usage,
  comms *counts* (not content), and coarse location entropy — with explicit,
  per-signal opt-in and on-device aggregation before upload.
- **Privacy:** on-device feature extraction (Gemini Nano) + differential privacy
  on uploaded features + federated baselines.

## References (representative, non-exhaustive)

- Onnela J-P, Rauch SL (2016). *Harnessing smartphone-based digital phenotyping…*
  Neuropsychopharmacology.
- Torous J, et al. (2016). *New tools for new research in psychiatry…* JMIR Mental Health.
- Al-Mosaiwi M, Johnson-Laird PN (2018). *In an absolute state: elevated use of
  absolutist words…* Clinical Psychological Science.
- Rude S, Gortner E-M, Pennebaker J (2004). *Language use of depressed and
  depression-vulnerable college students.* Cognition & Emotion.
- Tackman AM, et al. (2019). *Depression, negative emotionality, and self-referential
  language…* Journal of Personality and Social Psychology.
- Saeb S, et al. (2015). *Mobile phone sensor correlates of depressive symptom
  severity…* JMIR.
- Cummins N, et al. (2015). *A review of depression and suicide risk assessment
  using speech analysis.* Speech Communication.
- Kroenke K, Spitzer RL, Williams JBW (2001). *The PHQ-9.* J Gen Intern Med.
- Spitzer RL, et al. (2006). *A brief measure for assessing generalized anxiety
  disorder: the GAD-7.* Arch Intern Med.
