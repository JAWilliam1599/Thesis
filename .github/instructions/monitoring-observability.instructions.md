---
description: "Use when editing monitoring observability: CloudTrail, CloudWatch metrics/dashboards, ops-loop Lambda, stack monitoring, and on-prem SSM hybrid registration."
applyTo: "monitoring/**/*.py"
---

# Monitoring Observability Guidance

## Scope
- This file covers the Phase 4 observability and ops-loop layer in `monitoring/` only.
- Consume gate results and pipeline events; do not re-implement scoring (`security_gate/`) or deploy
  orchestration (`pipeline/`).

## Metrics, Events, and Contracts
- Keep the CloudWatch custom namespace, metric names (e.g. gate score / decision), and metric
  dimensions stable so dashboards and alarms keep resolving.
- Keep the EventBridge `GateDecision` event shape and SSM parameter layout consistent with the
  emitters in `pipeline/`.
- Use the target name (`<stack>` for CDK, `ansible-<node>` for on-prem) as the metric/SSM
  dimension so hybrid targets never collide.

## Ops Loop and Remediation
- Keep the ops-loop Lambda event-driven (AWS Config drift, CloudFormation rollback, SNS) and
  idempotent; avoid remediation actions that can loop or fight the pipeline.
- Preserve the three-layer monitoring model (gate metrics, config drift, audit trail) when
  attaching monitoring to a deployed stack.

## Robustness and Credentials
- Degrade gracefully: absent AWS credentials or missing resources must skip, not crash.
- Resolve AWS access through the shared credential path; never hardcode or log secrets.
- Register on-prem nodes as SSM managed instances via `ssm_hybrid.py`; reuse the existing
  compliance/ops-loop rather than adding a parallel path.
