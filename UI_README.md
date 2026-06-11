# UI Guide - Streamlit Control Plane

## Overview

The UI is now modularized under `ui/` and launched through `ui_app.py` (compatibility wrapper to `ui/main.py`).

This interface controls:
- generation and evaluation pipeline (Zone 1 to Zone 2 handoff)
- execution of generated code
- CDK deployment workflow with risk gate enforcement

## Run UI

```bash
streamlit run ui_app.py
```

## Tabs and Purpose

### 1) Run Pipeline

- submit prompt for code generation
- choose provider (`bedrock` or `openrouter`)
- set model, region, thresholds, and regeneration parameters
- view generated code and evaluation report

### 2) View Results

- inspect historical run artifacts from `ExecCode/run_<timestamp>/`
- compare passed and failed attempts

### 3) Exec Code

- run generated Python code in subprocess mode
- stream stdout/stderr to the UI

### 4) CDK Deploy

CDK gating flow in UI:
1. Prepare project in `GeneratedCDK/`
2. Run `cdk synth`
3. Auto-run IaC gate on synthesized templates
4. Run `cdk diff`
5. Allow `cdk deploy` only when gate decision allows

Gate decision logic:
- `pass` -> deploy allowed
- `review` -> deploy blocked until manual approval toggle
- `reject` -> deploy blocked

## CDK State and Logs

- Command output is streamed and persisted to `GeneratedCDK/command_logs/`
- Session state tracks:
  - synth status
  - diff status
  - gate report
  - manual review approval flag

## Configuration

- Bedrock credentials via AWS env vars
- OpenRouter key via input field or `OPENROUTER_API_KEY`
- CDK region/account resolved from environment and local AWS identity

## Known Scope

Implemented in UI:
- synth -> gate -> diff -> deploy gating flow
- review override support

Not yet exposed as full UI integrations:
- live Checkov/cfn-lint invocation and merged display
- live Infracost execution and parsed delta
- EventBridge/Lambda remediation loop controls

See `CDK-ONLY-NEXT-STEPS.md` for the backlog and execution order.

