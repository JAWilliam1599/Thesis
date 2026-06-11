# CDK-Only Pipeline - Next Steps

## Goal

Move from the current partial SysSecOps implementation to a production-ready CDK-only pipeline:

`generate -> eval -> cdk synth -> security/cost gate -> cdk diff -> deploy/deny -> monitor -> feedback`

## Current State Summary

Implemented now:
- CDK execution flow in CLI (`scripts/run_cdk_pipeline.py`)
- CDK execution flow in UI (`ui` CDK tab)
- IaC gate scoring and decisions in `Eval/iac_security_gate.py`
- Manual approval path for review-range score (21-60)
- Command logs in `GeneratedCDK/command_logs/`

Gaps vs SysSecOps target document:
- No real Checkov ingestion in gate score
- No real cfn-lint ingestion in gate score
- Infracost input is manual numeric parameter, not CLI integration
- AWS Config violations are manual numeric parameter, not automated pull
- No EventBridge/Lambda remediation loop yet
- No persistent risk store in SSM Parameter Store yet
- No Telegram/SNS approval and rejection notifications yet

## Priority Plan (CDK-Only)

### Phase 1 - Hard Gate Completion (Must Have)

1. Add scanner adapters in Eval
- Add `Eval/scanners/checkov_adapter.py`
- Add `Eval/scanners/cfn_lint_adapter.py`
- Input: synthesized templates from `GeneratedCDK/cdk.out`
- Output: normalized findings schema:
  - severity
  - source
  - message
  - resource_id
  - template

2. Merge scanner findings in `iac_security_gate.py`
- Combine built-in heuristics + Checkov + cfn-lint findings
- De-duplicate by `(source, resource_id, message)`
- Keep existing severity weights and thresholds

3. Enforce gate before diff/deploy in all entry points
- Ensure both UI and CLI fail closed if gate fails
- Block deploy when gate report is missing

Definition of done:
- Gate score reflects real scanner outputs
- Reject path reliably blocks deploy
- Review path requires explicit approval

### Phase 2 - Cost and Config Automation (Should Have)

1. Infracost integration
- Add adapter: `Eval/scanners/infracost_adapter.py`
- Run against CDK plan/synth artifacts where applicable
- Parse delta and map to existing cost points (+15/+40)

2. AWS Config integration
- Add fetch module for violations count by stack/resources
- Feed violations into `aws_config_violations` component automatically

3. Persist gate reports
- Save full gate report JSON under:
  - `logs/gate_reports/<run_id>.json`
  - optional copy in `GeneratedCDK/command_logs/`

Definition of done:
- No manual numeric cost/config inputs required in normal flow
- Every run has an auditable gate report artifact

### Phase 3 - Deployment Governance and Feedback (Should Have)

1. Notification hooks
- Add SNS/Telegram notifier for:
  - review-required
  - reject
  - deploy success/failure

2. Decision audit trail
- Record who approved review decisions and when
- Persist approvals with run ID

3. Regeneration feedback loop
- On reject, create structured feedback payload for Zone 1 prompt regeneration

Definition of done:
- Human review path is auditable
- Reject decisions automatically produce actionable feedback

### Phase 4 - Ops Loop (Nice to Have, then scale)

1. EventBridge + Lambda re-trigger path
- On AWS Config or compliance events, re-run gate scoring
- Optionally trigger controlled re-deploy/review process

2. SSM Parameter Store integration
- Store latest risk score and decision per stack/environment

3. Dashboard integration
- Expose gate trend and last decision in monitoring UI

Definition of done:
- Operational drift can trigger re-evaluation
- Risk status is queryable without opening log files

## Recommended File-Level Backlog

- `Eval/iac_security_gate.py`
  - add merged scanner pipeline and report metadata
- `pipeline/cdk_pipeline.py`
  - add stronger preconditions and structured error codes
- `scripts/run_cdk_pipeline.py`
  - add scanner toggles and output artifact path controls
- `ui/cdk_control.py`
  - add scanner result panel + reviewer approval capture
- `Eval/README.md`
  - keep scanner matrix updated as integrations land

## Suggested Execution Order (1-Week Sprint)

Day 1:
- implement Checkov adapter
- wire into gate score

Day 2:
- implement cfn-lint adapter
- merge and de-duplicate findings

Day 3:
- add gate report persistence
- update CLI output contract

Day 4:
- add Infracost adapter (basic)
- add auto cost ingestion path

Day 5:
- add review/reject notifications
- final integration test across UI + CLI

## Acceptance Criteria for "CDK-Only Ready"

1. `cdk deploy` cannot run when gate decision is `reject`.
2. `review` decision requires explicit manual approval and records approver metadata.
3. Score is computed from real scanner outputs plus cost/config signals.
4. Every pipeline run produces a gate report artifact with full findings.
5. UI and CLI produce consistent decisions for the same synthesized templates.

## Minimal Commands to Validate After Implementation

```bash
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --deploy
streamlit run ui_app.py
```

Run one known-safe stack and one intentionally unsafe stack (for example, open SSH to world) to verify pass and reject behavior.
