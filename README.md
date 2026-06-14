# SysSecOps Hybrid IaC Pipeline

This repository implements a practical subset of your SysSecOps model, with a working CDK-first deployment path and a risk gate between `cdk synth` and `cdk deploy`.

## Current End-to-End Flow

1. Generate IaC-oriented Python code (`AIgen/`)
2. Evaluate generated code for quality/security (`Eval/`)
3. Prepare CDK project in `GeneratedCDK/`
4. Run `cdk synth`
5. Run IaC security gate — heuristics + Checkov + cfn-lint + Infracost + AWS Config (`Eval/iac_security_gate.py`)
6. Persist gate report to `logs/gate_reports/`
7. Run `cdk diff`
8. Allow `cdk deploy` only when gate decision allows it
9. Send SNS notification on review / reject / deploy outcome
10. Write approval or rejection record to `logs/approvals/` or `logs/rejections/`
11. On reject, optionally auto-regen CDK code and retry (`AIgen/run_cdk_regen.py`)

This aligns with Zone 1 and Zone 2 in `SysSecOps-hybrid-with-RiskScringEngine-integrated-to-IaCSecurityGate.md`.

## Repository Structure

| Path | Role in pipeline |
|---|---|
| `AIgen/` | LLM generation (Bedrock/OpenRouter) + generation/eval orchestration |
| `AIgen/run_cdk_regen.py` | CDK-specific regen loop: generate → synth → gate → retry on reject |
| `Eval/` | Validation, security analysis, risk scoring, IaC gate |
| `Eval/scanners/` | Pluggable scanner adapters (Checkov, cfn-lint, Infracost, AWS Config) |
| `pipeline/` | CDK command runner + deploy decision logic |
| `pipeline/notifier.py` | AWS SNS notifier for gate and deploy events |
| `scripts/run_cdk_pipeline.py` | CLI pipeline: synth → gate → diff → optional deploy |
| `ui/` | Streamlit UI modules including `CDK Deploy` control tab |
| `ui_app.py` | Backward-compatible launcher that calls `ui/main.py` |
| `GeneratedCDK/` | Generated CDK app and command logs |
| `logs/gate_reports/` | Persisted gate report JSON files (one per run) |
| `logs/approvals/` | Persisted approval records with AWS ARN of approver |
| `logs/rejections/` | Persisted rejection records with top findings |
| `logs/cdk_regen/` | Per-run artifacts from CDK regen loop (prompts, code, gate reports) |
| `ExecComponent/` | Safe subprocess execution helpers |
| `ExecCode/` | Generated code outputs and per-run artifacts |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

External CLI tools (not pip-installable):
- `cdk` — AWS CDK CLI (`npm install -g aws-cdk`)
- `infracost` — cost analysis (`infracost auth login` after install)
- `checkov` — IaC security scanner (included in `requirements.txt`)
- `cfn-lint` — CloudFormation linter (included in `requirements.txt`)

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
# Full run — all scanners auto-enabled
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK

# Fast run — skip external scanners
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --no-checkov --no-cfn-lint

# Override cost/config manually
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --cost-delta-usd 25.0 --aws-config-violations 2

# Manual approve + deploy
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --manual-approve --deploy
```

### CLI flags reference

| Flag | Default | Description |
|---|---|---|
| `--project-dir` | `GeneratedCDK` | CDK project directory |
| `--run-id` | auto-generated | Override gate report filename |
| `--cost-delta-usd` | auto (Infracost) | Override monthly cost delta in USD |
| `--aws-config-violations` | auto (boto3) | Override AWS Config violation count |
| `--no-infracost` | off | Skip Infracost cost analysis |
| `--no-aws-config` | off | Skip AWS Config fetch |
| `--no-checkov` | off | Skip Checkov scan |
| `--no-cfn-lint` | off | Skip cfn-lint scan |
| `--manual-approve` | off | Approve review-band score (21–60) |
| `--deploy` | off | Run `cdk deploy` if gate allows |
| `--bootstrap` | off | Run `cdk bootstrap` first |
| `--prompt` | — | Original CDK request (used with `--regen-on-reject`) |
| `--regen-on-reject` | off | On gate reject, invoke CDK regen loop |
| `--max-regen-attempts` | `2` | Max regen loop attempts (used with `--regen-on-reject`) |
| `--approve-run-id` | — | Approve an existing review-band report by run ID |

## Streamlit UI

Run:

```bash
streamlit run ui_app.py
```

The `CDK Deploy` tab supports:
- preparing generated code as `GeneratedCDK/app.py`
- running `cdk synth`
- running the full gate (heuristics + Checkov + cfn-lint + Infracost + AWS Config)
- persisting gate report automatically
- running `cdk diff`
- enforcing deploy gating with optional manual review approval for score 21–60
- writing approval records (with AWS ARN) when the review toggle is checked
- writing rejection records automatically on gate reject
- sending SNS notifications on gate and deploy events (when `SNS_TOPIC_ARN` is set)

## IaC Risk Gate Model (Implemented)

Implemented in `Eval/iac_security_gate.py`.

**Scanner inputs:**

| Scanner | Source | Status |
|---|---|---|
| Heuristics | `iac_security_gate.py` | Always runs |
| Checkov | `Eval/scanners/checkov_adapter.py` | Graceful degradation |
| cfn-lint | `Eval/scanners/cfn_lint_adapter.py` | Graceful degradation |
| Infracost | `Eval/scanners/infracost_adapter.py` | Graceful degradation |
| AWS Config | `Eval/scanners/aws_config_adapter.py` | Graceful degradation |

**Scoring:**
- `CRITICAL × 30`, `HIGH × 10`, `MEDIUM × 5`, `LOW × 1`
- `cost_delta_usd > $10`: +15 pts | `> $50`: +40 pts
- `aws_config_violations × 5` pts

**Decision thresholds:**
- `0–20`: `pass` — auto deploy allowed
- `21–60`: `review` — manual approval required
- `> 60`: `reject` — blocked

**Gate reports** are persisted to `logs/gate_reports/gate_<run_id>.json` on every run.

## Deployment Governance (Phase 3)

### SNS Notifications (`pipeline/notifier.py`)

Set `SNS_TOPIC_ARN` to enable. Never blocks the pipeline on failure.

```bash
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:my-topic
```

Events published: `review_required`, `reject`, `deploy_success`, `deploy_failure`.

Message payload includes: `run_id`, `decision`, `score`, `top_findings` (first 5), `timestamp`, `event_type`.

### Audit Trail (`logs/approvals/`, `logs/rejections/`)

Every approval writes `logs/approvals/approval_<run_id>.json`:
```json
{
  "run_id": "cdk_20260614T124939Z",
  "approved_at": "2026-06-14T12:50:12Z",
  "approver": "cli",
  "approver_arn": "arn:aws:iam::926208928139:user/NguyenThong",
  "approver_account": "926208928139",
  "gate_decision": "review",
  "gate_score": 35
}
```

Every gate reject writes `logs/rejections/rejection_<run_id>.json` with the same identity fields plus `top_findings`.

ARN is resolved via `aws sts get-caller-identity` (CLI), falls back to `null` if unavailable.

### CDK Regen Loop (`AIgen/run_cdk_regen.py`)

Generates, synths, and gates in a loop — retrying on synth failure or gate reject.
Findings from the gate report are injected back into the regeneration prompt.

```bash
# Standalone regen loop
python AIgen/run_cdk_regen.py \
  --prompt "Create an S3 bucket with versioning and encryption" \
  --project-dir GeneratedCDK \
  --max-attempts 5 \
  --provider openrouter

# Regen triggered from main pipeline on reject
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --regen-on-reject \
  --max-regen-attempts 3 \
  --prompt "Create an S3 bucket with versioning and encryption"
```

Artifacts: `logs/cdk_regen/<run_id>/attempt_<N>/` (prompt, code, gate report, synth output).

## Documentation Index

- `AIgen/README.md` — generation providers and regen loop
- `Eval/README.md` — gate scoring, scanner adapters, report structure
- `ExecComponent/README.md` — subprocess execution helpers
- `UI_README.md` — Streamlit UI guide
- `CDK-ONLY-NEXT-STEPS.md` — implementation roadmap (Phases 1–4)
