# Eval - Zone 2 Security Gate and Scoring

## Purpose

`Eval/` implements Zone 2 in the SysSecOps model:
- validate generated Python code
- score risk and quality
- gate CDK deployments via synthesized-template checks

## Files

| File | Role |
|---|---|
| `main.py` | Evaluation coordinator |
| `quickVal.py` | Syntax and heuristic checks |
| `securityAnalysis.py` | Security scanner aggregation |
| `riskScoring.py` | Risk scoring for generated code |
| `evaluate_generated_code.py` | CLI entry point for code evaluation |
| `iac_security_gate.py` | CDK synth template analyzer + deployment gate score |

## Scanner Adapters (`Eval/scanners/`)

| Adapter | Scanner | Status | Graceful degradation |
|---|---|---|---|
| `checkov_adapter.py` | Checkov | Phase 1 | `not_installed`, `error`, `skipped` |
| `cfn_lint_adapter.py` | cfn-lint | Phase 1 | `not_installed`, `error`, `skipped` |
| `infracost_adapter.py` | Infracost CLI | Phase 2 | `not_installed`, `not_supported`, `error` |
| `aws_config_adapter.py` | AWS Config (boto3) | Phase 2 | `not_installed`, `no_credentials`, `not_configured`, `error` |

All adapters return a dict with at minimum: `{status, message}` plus adapter-specific fields. The gate merges all findings and scores them together.

## A. Generated Code Evaluation

Evaluate generated Python file:

```bash
python Eval/evaluate_generated_code.py --file ExecCode/generated_code.py
```

With deployment context:

```bash
python Eval/evaluate_generated_code.py --file ExecCode/generated_code.py --deployment-context internal
```

Primary report keys consumed by pipeline/UI:
- `score`
- `approval`
- `risk_level`
- `risk_score`
- `issues`
- `security_analysis`

## B. IaC Security Gate for CDK

`iac_security_gate.py` analyzes synthesized CloudFormation templates in `cdk.out` and returns a gate report.

### Evaluate signature

```python
gate.evaluate(
    cdk_out_dir,           # Path to cdk.out/
    cost_delta_usd=None,   # None = auto-run Infracost; float = override
    aws_config_violations=None,  # None = auto-fetch via boto3; int = override
    use_checkov=True,
    use_cfn_lint=True,
    use_infracost=True,
    use_aws_config=True,
    run_id=None,           # When set, report is persisted to logs/gate_reports/
    region=None,
    stack_name=None,
)
```

### Gate report structure

```json
{
  "run_id": "cdk_20260614T093934Z",
  "timestamp": "2026-06-14T09:39:42+00:00",
  "score": 90,
  "decision": "reject",
  "message": "Auto-reject. Regenerate IaC or remediate findings.",
  "components": { "severity": 60, "cost": 15, "aws_config": 15 },
  "inputs": {
    "cost_delta_usd": 49.63,
    "cost_delta_override": false,
    "aws_config_violations": 3,
    "aws_config_override": false
  },
  "scanner_status": {
    "checkov": "ok",
    "cfn_lint": "ok",
    "infracost": "ok",
    "aws_config": "no_credentials"
  },
  "scanner_warnings": [],
  "findings": [],
  "cost_analysis": { "status": "ok", "cost_delta_usd": 49.63, "template_count": 4 },
  "config_analysis": { "status": "no_credentials", "violation_count": 0 },
  "report_path": "/path/to/logs/gate_reports/gate_cdk_20260614T093934Z.json"
}
```

### Gate report persistence

Reports are saved automatically to `logs/gate_reports/gate_<run_id>.json` when `run_id` is provided. `save_report()` can also be called directly:

```python
path = gate.save_report(report, run_id="my_run")
```

### Current Rule Coverage in IaC Gate

- Security Group public ingress (`0.0.0.0/0`, SSH critical)
- S3 public access block enforcement
- S3 public ACL detection
- IAM policy wildcard action/resource detection
- RDS encryption check
- EBS volume encryption check

### Scoring and Decisions

- Severity points:
  - `critical`: 30
  - `high`: 10
  - `medium`: 5
  - `low`: 1
- Cost adjustment:
  - `cost_delta_usd > $10`: +15
  - `cost_delta_usd > $50`: +40
- AWS Config adjustment:
  - `aws_config_violations × 5`

Decision thresholds:
- `0–20`: `pass`
- `21–60`: `review`
- `> 60`: `reject`

## Integration with CDK Pipeline

`pipeline/cdk_pipeline.py` uses this module to enforce deploy gating:
1. `cdk synth`
2. `run_iac_gate(project_dir, run_id=run_id, region=region)` — auto-runs all scanners
3. `cdk diff`
4. `can_deploy(gate_report, manual_review_approved=...)` — final decision

Manual review approval is required for `review` decisions before deploy.

## Override Logic

Cost and AWS Config values follow this priority:
1. Explicit CLI arg / caller param (e.g. `--cost-delta-usd 25.0`) → used directly
2. Auto-detected (Infracost / boto3) → used when no explicit value
3. Graceful degradation → 0.0 / 0 if tool unavailable, gate still proceeds

## SysSecOps Comparison

Implemented (Phase 1 + Phase 2):
- risk gate between synth and deploy
- score-based pass/review/reject behavior
- Checkov and cfn-lint scanner ingestion
- Infracost CLI auto-cost analysis
- AWS Config auto-violations fetch via boto3
- gate report persistence to `logs/gate_reports/`

Planned next (Phase 3):
- SNS/Telegram notifications on reject/review/deploy
- decision audit trail with approver metadata
- regeneration feedback loop on reject

See `CDK-ONLY-NEXT-STEPS.md` for the full roadmap.
