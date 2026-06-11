---
description: "Use when editing ExecComponent runtime execution helpers, subprocess capture, and execution result contracts."
applyTo: "ExecComponent/**/*.py"
---

# ExecComponent Runtime Guidance

## Scope
- This file covers reusable runtime helpers in ExecComponent.
- Do not place project-level orchestration logic in this folder.

## Execution Safety and Behavior
- Prefer subprocess execution helpers for running generated files over inline exec behavior.
- Preserve stdout/stderr capture behavior expected by UI and pipeline consumers.

## Return Contracts
- Keep return shapes stable, including return_code and output fields.
- Do not silently change key names used by callers.

## Error Handling
- Propagate execution failures in structured results.
- Preserve line-by-line output handling hooks used by callers.
