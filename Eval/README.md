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

`iac_security_gate.py` analyzes synthesized CloudFormation templates in `cdk.out` and returns a gate report:

```json
{
  "score": 25,
  "decision": "review",
  "message": "Manual review required before deployment.",
  "components": {
    "severity": 10,
    "cost": 15,
    "aws_config": 0
  },
  "findings": []
}
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
  - `cost_delta_usd > 10`: +15
  - `cost_delta_usd > 50`: +40
- AWS Config adjustment:
  - `aws_config_violations * 5`

Decision thresholds:
- `0-20`: `pass`
- `21-60`: `review`
- `>60`: `reject`

## Integration with CDK Pipeline

`pipeline/cdk_pipeline.py` uses this module to enforce deploy gating:
1. `cdk synth`
2. `run_iac_gate(...)`
3. `cdk diff`
4. `can_deploy(...)` decision

Manual review approval is required for `review` decisions before deploy.

## SysSecOps Comparison

Implemented now:
- risk gate between synth and deploy
- score-based pass/review/reject behavior
- optional cost and AWS Config signals as numeric inputs

Planned next (not fully integrated yet):
- Checkov/cfn-lint scanner ingestion into the same gate report
- Infracost CLI automation
- live AWS Config/EventBridge feedback loop

See `CDK-ONLY-NEXT-STEPS.md` for the step-by-step implementation plan.
