---
description: "Use when editing pipeline orchestration: CDK/Ansible synth-gate-diff-deploy flow, approval/rejection audit trail, credentials, SSM/EventBridge/SNS Phase 4 governance."
applyTo: "pipeline/**/*.py"
---

# Pipeline Orchestration Guidance

## Scope
- This file covers the orchestration layer in `pipeline/` only (CDK + Ansible flow,
  governance, Phase 4 emitters).
- Do not embed code-generation logic (keep it in `generation/`) or scanner/scoring logic
  (keep it in `security_gate/`); call those interfaces instead.

## Deploy Decision and Governance
- Preserve the gate-driven decision: `pass` auto-deploys, `review` requires an explicit
  approval before deploy, `reject` never deploys.
- Never let `cdk deploy` / `ansible-playbook` run unless the gate decision (or a recorded
  manual approval) allows it.
- Keep the approval/rejection audit trail immutable and complete: record the approver's AWS
  identity, run ID, score, and decision under `logs/approvals/` and `logs/rejections/`.

## Execution Contracts
- Route external commands through `execution` subprocess helpers; preserve the
  `{return_code, output}` contract and stdout/stderr ordering.
- Mirror the `synth → diff → deploy` (CDK) and `syntax-check → --check → deploy` (Ansible)
  staging; do not skip the dry-run stage.
- Keep the `SYSSECOPS_LOG_DIR` override honored so per-project artifact isolation works.

## Phase 4 Observability
- Keep observability emitters (SSM persist, EventBridge `GateDecision` event, CloudWatch
  metrics/logs, SNS) best-effort: missing AWS credentials must skip silently, never crash.
- Keep SSM parameter layout and EventBridge event shape stable for `monitoring/` and UI readers.

## Credentials
- Resolve credentials through `aws_credentials.py` (boto3 chain + SSO export); never accept
  secrets as CLI arguments or log them.
