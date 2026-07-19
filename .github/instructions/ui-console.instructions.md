---
description: "Use when editing the Streamlit operator console: tabs, sidebar settings, credential handling, subprocess orchestration, project registry, and report/monitoring rendering."
applyTo: "ui/**/*.py"
---

# UI Operator Console Guidance

## Scope
- This file covers the Streamlit app in `ui/` only. Keep it a thin orchestration layer over
  the CLI scripts and read-only AWS queries.
- Do not embed generation, scanning, scoring, or deploy logic in the UI; delegate to
  `generation/`, `security_gate/`, and `pipeline/`/`scripts/` via subprocesses.

## Orchestration Contracts
- Launch privileged actions (generate, synth-gate, deploy) as subprocesses of the CLI scripts;
  interpret their return codes via `config.py::RETURN_CODE_MEANING`.
- Export the active project's log root through `SYSSECOPS_LOG_DIR` so subprocess artifacts land
  in the right per-project directory.
- Keep gate-report / approval / rejection discovery in `helpers.py` aligned with the on-disk
  layout produced by the pipeline.

## Credentials and Secrets
- Inject credentials into subprocesses via environment variables only — never as CLI
  arguments and never rendered in the UI.
- Persist AWS credentials to `~/.aws` and OpenRouter keys to `.env`; do not store secrets in
  session state longer than needed or write them to logs.

## Projects and State
- Preserve the multi-project registry (`projects.py`, `logs/projects.json`): the `default`
  project keeps the legacy flat `logs/` layout; others use `logs/projects/<id>/`.
- Keep session-state initialization centralized in `main.py`; keep tab rendering side-effect
  free apart from the delegated subprocess/AWS calls.
