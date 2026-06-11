# AIgen - Zone 1 Generation Module

## Purpose

`AIgen/` is the Zone 1 entry point in the SysSecOps model: generate IaC-oriented Python code from prompts, then hand off to evaluation and CDK deployment gate.

## Files

| File | Role |
|---|---|
| `bedrock_codegen.py` | Bedrock-based generation |
| `openrouter_codegen.py` | OpenRouter-based generation |
| `run_generation_and_eval.py` | Main orchestration: generate -> evaluate -> regenerate on failure |

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

## SysSecOps Alignment

Aligned:
- Zone 1 generation and feedback loop
- Structured failure feedback for regeneration

Not yet fully implemented in this module:
- strict prompt templates dedicated to CDK-only output format
- deterministic generation contract for multi-file CDK apps

Use `CDK-ONLY-NEXT-STEPS.md` in the repo root for implementation priorities.
