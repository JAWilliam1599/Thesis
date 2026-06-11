# SysSecOps Hybrid IaC Pipeline

This repository implements a practical subset of your SysSecOps model, with a working CDK-first deployment path and a risk gate between `cdk synth` and `cdk deploy`.

## Current End-to-End Flow

1. Generate IaC-oriented Python code (`AIgen/`)
2. Evaluate generated code for quality/security (`Eval/`)
3. Prepare CDK project in `GeneratedCDK/`
4. Run `cdk synth`
5. Run IaC security gate and risk scoring (`Eval/iac_security_gate.py`)
6. Run `cdk diff`
7. Allow `cdk deploy` only when gate decision allows it

This aligns with Zone 1 and Zone 2 in `SysSecOps-hybrid-with-RiskScringEngine-integrated-to-IaCSecurityGate.md`.

## Repository Structure

| Path | Role in pipeline |
|---|---|
| `AIgen/` | LLM generation (Bedrock/OpenRouter) + generation/eval orchestration |
| `Eval/` | Validation, security analysis, risk scoring, IaC gate |
| `pipeline/` | CDK command runner + deploy decision logic |
| `scripts/run_cdk_pipeline.py` | CLI pipeline: synth -> gate -> diff -> optional deploy |
| `ui/` | Streamlit UI modules including `CDK Deploy` control tab |
| `ui_app.py` | Backward-compatible launcher that calls `ui/main.py` |
| `GeneratedCDK/` | Generated CDK app and command logs |
| `ExecComponent/` | Safe subprocess execution helpers |
| `ExecCode/` | Generated code outputs and per-run artifacts |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set cloud credentials

```bash
export AWS_ACCESS_KEY_ID=<your_key>
export AWS_SECRET_ACCESS_KEY=<your_secret>
export AWS_REGION=us-east-1
```

Optional if using OpenRouter:

```bash
export OPENROUTER_API_KEY=<your_key>
```

### 3. Generate and evaluate code

```bash
python AIgen/run_generation_and_eval.py --prompt "Generate a secure AWS CDK Python app"
```

### 4. Run CDK pipeline with risk gate (CLI)

```bash
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK
```

Optional deploy after gate:

```bash
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --deploy
```

If decision is `review` (score 21-60), allow deploy with manual override:

```bash
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --manual-approve --deploy
```

## Streamlit UI

Run:

```bash
streamlit run ui_app.py
```

The `CDK Deploy` tab supports:
- preparing generated code as `GeneratedCDK/app.py`
- running `cdk synth`
- producing a gate report from synthesized templates
- running `cdk diff`
- enforcing deploy gating with optional manual review approval for score 21-60

## IaC Risk Gate Model (Implemented)

Implemented in `Eval/iac_security_gate.py`.

- Severity weights:
	- `CRITICAL x 30`
	- `HIGH x 10`
	- `MEDIUM x 5`
	- `LOW x 1`
- Cost adjustments:
	- `cost_delta_usd > 10`: `+15`
	- `cost_delta_usd > 50`: `+40`
- AWS Config signal:
	- `aws_config_violations * 5`
- Decision thresholds:
	- `0-20`: `pass`
	- `21-60`: `review`
	- `>60`: `reject`

## Important Notes

- The CDK gate currently analyzes synthesized CloudFormation templates and internal scoring inputs.
- Tool integrations named in the SysSecOps design (`Checkov`, `cfn-lint`, `Infracost`, `AWS Config` live feeds, EventBridge/Lambda remediation loop) are only partially implemented at this stage.
- Use `CDK-ONLY-NEXT-STEPS.md` for the concrete implementation roadmap.

## Documentation Index

- `AIgen/README.md`
- `Eval/README.md`
- `ExecComponent/README.md`
- `UI_README.md`
- `CDK-ONLY-NEXT-STEPS.md`
