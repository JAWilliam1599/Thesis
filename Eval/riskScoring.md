# RiskScoring Module Documentation

## File
- `Eval/riskScoring.py`

## Purpose
`riskScoring.py` provides a multi-factor risk scoring engine for security findings. It combines:
- finding severity,
- exploitability signals,
- deployment exposure,
- and confidence (cross-tool corroboration),

into a single numeric score (`0-100`) plus a policy decision (for example, block deployment).

## High-Level Flow
1. Accept source code (`code`) and a list of findings (`findings`).
2. Normalize finding messages to detect cross-tool duplicates.
3. Score each finding using four weighted components.
4. Convert each finding score into a risk level and recommended action.
5. Return:
   - overall score (maximum finding score),
   - overall level/action,
   - per-level/source summary,
   - per-finding detailed scoring breakdown.

## Data Structures

### `ScoredFinding` dataclass
Immutable model containing the scored output for one finding:
- `source`: normalized analyzer name (lowercase)
- `severity`: normalized severity label
- `message`: raw message text (trimmed)
- `severity_value`: mapped integer severity weight
- `severity_score`: normalized severity in `[0,1]`
- `exploitability_score`: exploitability in `[0,1]`
- `exposure_score`: exposure in `[0,1]`
- `confidence_score`: confidence in `[0,1]`
- `risk_score`: weighted score in `[0,100]`
- `risk_level`: one of `Critical | High | Medium | Low`
- `recommended_action`: policy action string
- `normalized_key`: normalized message fingerprint used for grouping

## Constants and Configuration

### Severity mapping
`SEVERITY_VALUE_MAP`:
- `critical -> 10`
- `high -> 8`
- `medium -> 5`
- `low -> 2`
- `warning -> 3`
- `info -> 1`

Unknown severities are treated as `low`.

### Risk thresholds and actions
`RISK_LEVELS`:
- `>= 80`: `Critical`, action `Block deployment`
- `>= 60`: `High`, action `Require manual approval`
- `>= 40`: `Medium`, action `Allow with warning`
- `>= 0`: `Low`, action `Log for monitoring`

### Exposure pattern sets
- `PUBLIC_FACING_PATTERNS`: route/server/network indicators (`fastapi`, `@app.route`, `request.`, `listen(`, etc.)
- `INTERNAL_PATTERNS`: internal/cloud service indicators (`boto3`, `aws`, `lambda`, etc.)
- `SANCDBOX_PATTERNS`: test/sandbox indicators (`pytest`, `unittest`, `sandbox`, etc.)

Note: the constant name is spelled `SANCDBOX_PATTERNS` in code (typo in identifier). Behavior is unaffected because references use the same identifier.

### Exploitability keyword sets
- `HIGH_EXPL_PATTERNS` returns `1.0` when matched
- `MEDIUM_EXPL_PATTERNS` returns `0.8`
- `LOW_EXPL_PATTERNS` returns `0.2`

If no keyword matches, source/severity fallbacks are used.

## `RiskScorer` Class

### Constructor
```python
RiskScorer(deployment_context: str | None = None)
```
- Normalizes context to lowercase.
- Defaults to `internal` when missing.

Supported contexts:
- `public`
- `internal`
- `onprem`
- `sandbox`
- any other value falls back to inferred exposure.

## Main API

### `score(code: str, findings: Iterable[dict]) -> dict`
Returns a dict with:
- `risk_score`: maximum per-finding score
- `risk_level`: level for `risk_score`
- `recommended_action`: action for `risk_score`
- `risk_summary`:
  - counts by risk level (`critical/high/medium/low`)
  - `sources`: finding count per source
- `risk_findings`: list of fully expanded scored findings

Important design detail:
- Overall score is `max` of finding scores, not an average. A single critical issue dominates the pipeline decision.

## Scoring Formula
Per finding:

\[
\text{risk\_score} = 100 \times \left(0.35\cdot S + 0.25\cdot E + 0.25\cdot X + 0.15\cdot C\right)
\]

Where:
- \(S\) = `severity_score`
- \(E\) = `exploitability_score`
- \(X\) = `exposure_score`
- \(C\) = `confidence_score`

All components are clamped logically by construction to the `[0,1]` interval.

## Method-by-Method Behavior

### `_score_finding(...)`
- Normalizes source/severity/message.
- Computes all component scores.
- Applies weighted formula.
- Classifies finding into level/action.
- Returns `ScoredFinding` with rounded values.

### `_normalize_severity(severity)`
- Lowercases and validates against `SEVERITY_VALUE_MAP`.
- Unknown values become `low`.

### `_normalize_message(message)`
Creates a stable, lossy fingerprint used for cross-tool matching:
- lowercase
- hex literals replaced with `<hex>`
- decimal numbers replaced with `<num>`
- strips most punctuation/symbol noise
- collapses whitespace
- truncates to 240 chars

### `_build_normalized_groups(findings)`
Builds:
- key: normalized message
- value: set of unique sources that reported it

Used by confidence scoring to reward corroboration.

### `_exploitability_score(source, severity, message, code)`
Process:
1. Search `message + code` for high/medium/low exploitability keywords.
2. If no match, apply source defaults:
   - `bandit`: severity-specific mapping (`critical` highest)
   - `semgrep`: severity-specific mapping
   - `quickval`: fixed `0.4`
   - others: `0.5`

### `_exposure_score(code)`
Context-aware exposure policy:
- `public`: always `1.0`
- `internal`: `max(0.6, inferred)`
- `onprem`: `min(inferred, 0.3)`
- `sandbox`: `min(inferred, 0.1)`
- unknown context: inferred only

### `_infer_exposure_from_code(code)`
Heuristic inference from code text:
- public-facing pattern match -> `1.0`
- internal/cloud pattern match -> `0.6`
- sandbox/test pattern match -> `0.1`
- `if __name__ == "__main__":` -> `0.6`
- default -> `0.6`

### `_confidence_score(source, severity, normalized_key, normalized_groups)`
Rules (in order):
- same normalized message reported by at least 2 sources -> `1.0`
- `bandit`/`semgrep` + high/critical -> `0.8`
- `quickval` -> `0.3`
- high/critical severity from other sources -> `0.8`
- medium -> `0.5`
- low/warning/info -> `0.4`

### `_classify(risk_score)`
Threshold walk over `RISK_LEVELS`, returns first match.

### `_summarize(findings)`
Counts:
- number of findings by computed risk level
- number of findings by source

## Input Contract
Expected finding fields (missing values are tolerated):
- `source` (default `unknown`)
- `severity` (default `low`)
- `message` (default empty string)

The scorer is defensive and coerces values via `str(...)`.

## Output Example
```json
{
  "risk_score": 84.5,
  "risk_level": "Critical",
  "recommended_action": "Block deployment",
  "risk_summary": {
    "critical": 1,
    "high": 2,
    "medium": 0,
    "low": 3,
    "sources": {
      "bandit": 2,
      "semgrep": 2,
      "quickval": 2
    }
  },
  "risk_findings": [
    {
      "source": "bandit",
      "severity": "high",
      "message": "Potential command injection...",
      "severity_value": 8,
      "severity_score": 0.8,
      "exploitability_score": 1.0,
      "exposure_score": 1.0,
      "confidence_score": 1.0,
      "risk_score": 91.0,
      "risk_level": "Critical",
      "recommended_action": "Block deployment",
      "normalized_key": "potential command injection ..."
    }
  ]
}
```

## Practical Notes
- The module is deterministic for identical input.
- Message normalization can merge semantically different findings if text is too similar after normalization.
- Using max finding score is conservative and suitable for deployment gates.
- Exposure inference is regex/keyword-based and should be considered heuristic.

## Suggested Enhancements
- Add type models for finding input schema.
- Externalize weight and threshold config for runtime tuning.
- Add unit tests for:
  - context-specific exposure behavior,
  - confidence multi-source grouping,
  - keyword precedence in exploitability,
  - unknown severity/source handling.
- Consider optional aggregated policies (`max`, `p95`, `weighted mean`) depending on deployment strategy.

## Minimal Usage Example
```python
from Eval.riskScoring import RiskScorer

code = """
from fastapi import FastAPI
app = FastAPI()
"""

findings = [
    {"source": "bandit", "severity": "high", "message": "Potential command injection via subprocess"},
    {"source": "semgrep", "severity": "medium", "message": "Possible unsafe use of user input"},
]

scorer = RiskScorer(deployment_context="internal")
result = scorer.score(code=code, findings=findings)
print(result["risk_level"], result["risk_score"])
```
