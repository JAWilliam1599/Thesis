# Code Generation & Evaluation Pipeline

## Overview

End-to-end pipeline for generating Python AWS SDK code using LLM models (Bedrock or OpenRouter) and evaluating generated code for security, quality, and correctness.

**Pipeline Flow:**
1. Generate Python AWS SDK code (AIgen/)
2. Save generated code (ExecCode/)
3. Evaluate with security + quality checks (Eval/)
4. Present results and feedback for regeneration (UI/orchestration)

## Project Structure

| Folder | Purpose |
|--------|---------|
| **AIgen/** | LLM code generation using Bedrock or OpenRouter APIs |
| **Eval/** | Multi-factor security and quality evaluation |
| **ExecCode/** | Generated code artifacts and run results |
| **ExecComponent/** | Runtime code execution utilities |
| **CreateExampleEnv/** | AWS CDK infrastructure example (standalone scope) |
| **Monitor/** | Placeholder for monitoring (currently unused) |
| **logs/** | Pipeline runtime logs |

## Quick Start

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure credentials
export AWS_ACCESS_KEY_ID=<your_key>
export AWS_SECRET_ACCESS_KEY=<your_secret>
export AWS_REGION=us-east-1
# Optional: set OPENROUTER_API_KEY if using OpenRouter provider
```

### Run Full Pipeline (Generate + Evaluate)

```bash
python AIgen/run_generation_and_eval.py --prompt "Create Python code that lists S3 buckets using boto3"
```

With auto-regeneration on failures:

```bash
python AIgen/run_generation_and_eval.py --prompt "..." --max-regen 2
```

### Run Generation Only

```bash
python AIgen/bedrock_codegen.py --prompt "Create Python code that uploads a file to S3"
```

With model validation:

```bash
python AIgen/bedrock_codegen.py --prompt "..." --validate-model
```

### Run Evaluation Only

```bash
python Eval/evaluate_generated_code.py --file ExecCode/generated_code.py
```

With custom deployment context:

```bash
python Eval/evaluate_generated_code.py --file ExecCode/generated_code.py --deployment-context internal
```

### Web UI (Streamlit)

```bash
streamlit run ui_app.py
```

### Desktop UI (tkinter)

```bash
python ui_desktop.py
```

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `AWS_ACCESS_KEY_ID` | AWS credentials for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for Bedrock |
| `AWS_REGION` | AWS region (default: `ap-southeast-2`) |
| `OPENROUTER_API_KEY` | OpenRouter API key if using OpenRouter |

### Model Configuration

- **Default Model ID:** `qwen.qwen3-coder-30b-a3b-v1:0`
- **Override:** Pass `--model-id <model_id>` to scripts
- **Validation:** Use `--validate-model` to verify availability

## Agent Context Instructions

Located in `.github/instructions/`:

- `aigen-domain.instructions.md` — Generation logic, provider selection, run artifacts
- `eval-security.instructions.md` — Evaluation, security analysis, risk scoring
- `execcomponent-runtime.instructions.md` — Execution helpers, subprocess contracts
- `root-pipeline.instructions.md` — Cross-module integration, environment setup
- `pipeline-entrypoints.instructions.md` — Critical coordinator file contracts

## Key Concepts

### Evaluation Report

Stable output keys (used downstream by UI and regeneration):
- `score` (0-100): quality score
- `approval` (bool): pass/fail determination
- `risk_level`: Low/Medium/High/Critical
- `risk_score` (float): numerical security risk
- `issues`: list of findings
- `security_analysis`: tool findings (bandit, semgrep, OWASP)

### Run Artifacts

Each pipeline run creates `ExecCode/run_<timestamp>/` with:
- `prompt.txt`: original user request
- `passed/`: successful generation snapshots
- `failed/`: failed attempts with reports

## Troubleshooting

**"Too many tokens per day" from Bedrock:**
- Check AWS Console > Bedrock > Service Quotas
- Request quota increases if needed

**Model not found:**
- Verify model ID exists in your Bedrock account
- Use `--validate-model` flag to test

**OpenRouter issues:**
- Set `OPENROUTER_API_KEY` environment variable
- UI will auto-fallback to env var if field empty

## Documentation

- [AIgen/README.md](AIgen/README.md) — Code generation details
- [Eval/README.md](Eval/README.md) — Evaluation logic
- [ExecCode/README.md](ExecCode/README.md) — Artifact storage
- [ExecComponent/README.md](ExecComponent/README.md) — Execution utilities
- [CreateExampleEnv/README.md](CreateExampleEnv/README.md) — Infrastructure example
- [riskScoring.md](riskScoring.md) — Risk scoring methodology
- [UI_README.md](UI_README.md) — User interface guide
