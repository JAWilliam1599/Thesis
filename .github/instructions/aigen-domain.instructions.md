---
description: "Use when working in AIgen code generation modules (Bedrock/OpenRouter), prompt handling, provider selection, run folder artifacts, and generation-evaluation handoff contracts."
applyTo: "AIgen/**/*.py"
---

# AIgen Domain Instructions

Scope
- This file governs code in `AIgen/**` only.
- Keep orchestration contracts with `Eval/main.py` stable when modifying generation flow.

Conventions
- Preserve provider abstraction between Bedrock and OpenRouter. Add provider-specific behavior behind provider flags, not branch-specific one-offs.
- Keep model defaults centralized and allow explicit CLI override (`--model-id`).
- Handle missing credentials and service errors with clear user-facing messages and non-zero exits.
- Preserve runtime artifact layout under `ExecCode/run_<timestamp>/` including prompt snapshot and pass/fail outputs.

Contracts
- Generated output paths and report snapshot semantics should remain compatible with UI readers and pipeline consumers.
- Regeneration prompts should be deterministic and include evaluation feedback as machine-readable JSON where possible.

Do Not
- Do not couple AIgen logic directly to UI rendering concerns.
- Do not duplicate risk scoring logic from `Eval/**`; call evaluator interfaces instead.---
description: "Use when editing AIgen generation logic, provider selection, model handling, and generation-to-evaluation handoff."
applyTo: "AIgen/**/*.py"
---

# AIgen Domain Guidance

## Scope
- This file covers code in AIgen only.
- Do not duplicate Eval scoring rules here.
- Do not add guidance for generated artifacts under ExecCode.

## Generation Contracts
- Keep generation output deterministic for the same prompt and provider inputs where possible.
- Preserve provider abstraction boundaries so Bedrock and OpenRouter implementations stay swappable.
- Keep return shapes stable for pipeline callers.

## Runtime and Artifacts
- Preserve runtime-id based run folder behavior used by orchestrator entrypoints.
- Keep prompt snapshot and run artifact paths consistent with existing run history layout.

## Provider and Credential Handling
- Bedrock-specific behavior should stay isolated from OpenRouter-specific behavior.
- Read API keys and region from explicit arguments first, then environment variables.
- Keep model-id override behavior explicit and validated when validation options are enabled.

## Error Handling
- Handle provider/API exceptions with actionable logs.
- Do not suppress quota, throttling, or auth errors; surface enough detail for retry decisions.
