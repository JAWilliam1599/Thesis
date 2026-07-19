---
description: "Use when editing security_gate logic for quick validation, security analysis, risk scoring, and evaluation report assembly."
applyTo: "security_gate/**/*.py"
---

# Security Gate Guidance

## Scope
- This file covers evaluation logic in security_gate only.
- Keep generation/provider behavior in generation, not here.

## Evaluation Flow
- Preserve the sequence: quick validation, security analysis, risk scoring, then approval decision.
- Keep report keys and field names stable so UI and pipeline consumers do not break.

## Risk Scoring Consistency
- Keep weighting and severity normalization aligned with risk scoring documentation.
- Deployment context handling must remain explicit and predictable.

## Security Findings
- Normalize findings into consistent structures before scoring.
- Preserve clear separation between blocking issues and warnings.

## Approval and Thresholds
- Keep approval semantics explicit and deterministic.
- Maintain clear behavior for fail-below thresholds and non-zero exits in CLI wrappers.
