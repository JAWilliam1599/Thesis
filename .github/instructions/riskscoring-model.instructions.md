---
description: "Use when editing the risk-scoring model training/citation code: dataset assembly, feature extraction (bandit/semgrep), logistic-regression training, and gate handoff."
applyTo: "RiskScoringCitation/**/*.py"
---

# Risk Scoring Model Guidance

## Scope
- This file covers the ML risk-scoring research/training code in `RiskScoringCitation/` only.
- This code trains and evaluates the model consumed at gate time by
  `Eval/scanners/ml_risk_adapter.py`; keep the two in lockstep.

## Feature and Training Consistency
- Keep feature extraction (tools used, severity mapping, per-file scanning) identical between
  training here and inference in `ml_risk_adapter.py`, so inference matches the training
  distribution. If features change here, update the adapter in the same change.
- Keep the persisted model artifacts (`.pkl`) and their expected location stable, or update
  every consumer that loads them.
- Keep dataset schema and label semantics (secure vs. insecure) explicit and documented.

## Reproducibility and Rigor
- Prefer deterministic training (fixed random seeds, recorded splits) so results are
  reproducible for the thesis evaluation.
- Report evaluation metrics honestly (accuracy plus precision/recall/AUC where relevant); do
  not overstate performance.
- Keep data-preparation, training, and inference steps separable and re-runnable from scratch.

## Do Not
- Do not couple training code to pipeline runtime or UI concerns.
- Do not silently change the probability-to-points mapping without updating the gate
  (`ML_MAX_POINTS` and the adapter).
