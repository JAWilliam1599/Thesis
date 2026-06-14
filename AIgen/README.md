# AIgen - Zone 1 Generation Module

## Purpose

`AIgen/` is the Zone 1 entry point in the SysSecOps model: generate IaC-oriented Python code from prompts, then hand off to evaluation and CDK deployment gate.

## Files

| File | Role |
|---|---|
| `bedrock_codegen.py` | Bedrock-based generation |
| `openrouter_codegen.py` | OpenRouter-based generation |
| `run_generation_and_eval.py` | Main orchestration: generate → evaluate → regenerate on failure |
| `run_cdk_regen.py` | CDK-specific regen loop: generate → synth → gate → retry on reject |

## Typical Flow

1. User prompt requests infrastructure code
2. Provider generates Python output
3. Output is stored in `ExecCode/`
4. `Eval/` returns structured report (`score`, `approval`, `issues`, risk fields)
5. On failure, regeneration includes report feedback
6. On pass, output can be prepared for CDK stage (`GeneratedCDK/`)

## CLI Usage

Generate only:

```bash
python AIgen/bedrock_codegen.py --prompt "Create secure AWS CDK Python stack"
```

Generate + evaluate + optional regeneration:

```bash
python AIgen/run_generation_and_eval.py --prompt "Create secure AWS CDK Python stack" --max-regen 2
```

Use OpenRouter provider:

```bash
python AIgen/run_generation_and_eval.py --provider openrouter --prompt "Create secure AWS CDK Python stack"
```

## Key Options (`run_generation_and_eval.py`)

| Option | Description |
|---|---|
| `--provider` | `bedrock` or `openrouter` |
| `--prompt` | Generation prompt |
| `--model-id` | Provider model ID |
| `--region` | AWS region for Bedrock |
| `--api-key` | OpenRouter API key override |
| `--fail-below` | Evaluation threshold for regeneration |
| `--max-regen` | Max regeneration attempts |
| `--deployment-context` | `public`, `internal`, `onprem`, `sandbox` |
| `--verbose` | Detailed logs |

## Provider Configuration

- Bedrock uses `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`.
- OpenRouter uses `OPENROUTER_API_KEY` (or `--api-key`).
- Avoid hardcoded credentials.

## Handoff Contract to Eval

This module relies on stable report keys from `Eval/`:
- `score`
- `approval`
- `risk_level`
- `risk_score`
- `issues`
- `security_analysis`

These fields feed both regeneration prompts and UI decisions.

## Outputs

- Current artifact: `ExecCode/generated_code.py`
- Run artifacts: `ExecCode/run_<timestamp>/` with `passed/` and `failed/` attempts
- CDK regen artifacts: `logs/cdk_regen/<run_id>/attempt_<N>/` (prompt, code, gate report, synth output)

## CDK Regen Loop (`run_cdk_regen.py`)

A CDK-specific generation loop that uses gate findings as structured feedback for regeneration.

```bash
# Standalone — generates, synths, gates, retries on failure
python AIgen/run_cdk_regen.py \
  --prompt "Create an S3 bucket with versioning and encryption" \
  --project-dir GeneratedCDK \
  --max-attempts 5 \
  --provider openrouter \
  --api-key sk-or-...
```

| Option | Description |
|---|---|
| `--prompt` | Infrastructure request |
| `--project-dir` | CDK project directory (default: `GeneratedCDK`) |
| `--max-attempts` | Max regen attempts (default: 2) |
| `--provider` | `bedrock` or `openrouter` |
| `--model-id` | Model ID override |
| `--region` | AWS region (Bedrock) |
| `--api-key` | OpenRouter API key |
| `--run-id` | Override auto-generated run ID |

**Loop behaviour:**
1. Generate code → write to `GeneratedCDK/app.py`
2. `cdk synth` — on failure, synth error is cleaned (jsii banner stripped) and injected into next prompt along with the failing code
3. IaC gate — on `reject`, findings are injected into next regen prompt
4. On `pass` or `review`, save to `logs/cdk_regen/<run_id>/passed/` and return success
5. On exhaustion, save to `logs/cdk_regen/<run_id>/failed/` and return failure

The loop can also be triggered from the main CLI pipeline on gate reject:

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --regen-on-reject \
  --max-regen-attempts 3 \
  --prompt "Create an S3 bucket with versioning and encryption"
```

## SysSecOps Alignment

Implemented (Phase 1 + Phase 3):
- Zone 1 generation and feedback loop
- Structured failure feedback for regeneration
- CDK-specific regen loop with gate findings injected into prompts
- Provider abstraction (Bedrock / OpenRouter) preserved across both loops

Not yet fully implemented in this module:
- strict prompt templates dedicated to CDK-only output format
- deterministic generation contract for multi-file CDK apps

Use `CDK-ONLY-NEXT-STEPS.md` in the repo root for implementation priorities.
