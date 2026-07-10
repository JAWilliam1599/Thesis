---
description: "Use when working in AIgen code generation modules (Bedrock/OpenRouter), prompt handling, provider selection, run folder artifacts, and generation-evaluation handoff contracts."
applyTo: "AIgen/**/*.py"
---

# AIgen Domain Instructions

## Scope
- This file governs code in `AIgen/**` only.
- Keep the handoff contract with the security gate (`Eval/iac_security_gate.py`) stable when
  modifying generation flow — the regen loop consumes the gate report JSON verbatim.
- Do not duplicate risk-scoring logic from `Eval/**`; call the evaluator via the pipeline
  instead.

## Generation Contracts
- Preserve the provider abstraction between Bedrock and OpenRouter. Add provider-specific
  behavior behind provider flags, not branch-specific one-offs, so the two implementations
  stay swappable.
- Keep model defaults centralized and allow explicit CLI override (`--model-id`).
- Keep generation output deterministic for the same prompt and provider inputs where possible.
- Keep return shapes stable for pipeline callers.

## Runtime and Artifacts
- Preserve the CDK regen run-folder layout under
  `logs/cdk_regen/<run_id>/attempt_<N>/` (prompt snapshot, generated code, synth output, and
  gate report) plus the `logs/cdk_regen/<run_id>/passed/` promotion folder on success.
- Keep prompt snapshots and artifact paths consistent with existing run history so UI readers
  and pipeline consumers keep working.
- Regeneration prompts should be deterministic and inject the gate findings as machine-readable
  JSON so the loop converges within the attempt budget.

## Provider and Credential Handling
- Keep Bedrock-specific behavior isolated from OpenRouter-specific behavior.
- Read API keys and region from explicit arguments first, then environment variables.
- Keep the model-id override explicit and validated when validation options are enabled.

## Error Handling
- Handle missing credentials and provider/API exceptions with clear, actionable, user-facing
  messages and non-zero exits.
- Do not suppress quota, throttling, or auth errors; surface enough detail for retry decisions.

## Do Not
- Do not couple AIgen logic directly to UI rendering concerns.
- Do not duplicate risk-scoring logic from `Eval/**`; call evaluator interfaces instead.
