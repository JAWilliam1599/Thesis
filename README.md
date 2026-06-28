# SysSecOps Hybrid IaC Pipeline

This repository implements a practical subset of the SysSecOps model, with a CDK-first deployment path, a multi-scanner risk gate between `cdk synth` and `cdk deploy`, and a full Phase 4 ops loop providing real-time observability and security monitoring.

## End-to-End Flow

1. Generate synthesizable CDK (Python) code from a prompt (`AIgen/`)
2. Write the generated app to `GeneratedCDK/app.py`
3. Clear `cdk.out/` to prevent stale template accumulation
4. Run `cdk synth`
5. Run IaC security gate — heuristics + Checkov + cfn-lint + Infracost + AWS Config (`Eval/iac_security_gate.py`)
6. Persist gate report to `logs/gate_reports/`
7. **Phase 4:** Emit gate observability — SSM persist + EventBridge event + CloudWatch metrics + CloudWatch logs
8. Run `cdk diff`
9. Allow `cdk deploy` only when the gate decision allows it
10. Send SNS notification on review / reject / deploy outcome
11. Write approval or rejection record to `logs/approvals/` or `logs/rejections/`
12. **Phase 4:** Attach 3-layer security monitoring to deployed stack (Application Insights + metric alarms + CloudTrail/VPC flow alarms)
13. On reject, optionally auto-regen CDK code and retry (`AIgen/run_cdk_regen.py`)

This aligns with Zone 1 and Zone 2 in `SysSecOps-hybrid-with-RiskScringEngine-integrated-to-IaCSecurityGate.md`.

## Hybrid Mode (CDK + on-prem Ansible)

The hybrid path extends the same gate / risk-scoring / deploy / observability
workflow to an on-prem **Ansible** target — **without any code-generation step**
(both the CDK app and the Ansible playbooks are bring-your-own code that already
exist in the repo). You point the pipeline at two existing paths and it gates
each side independently with the same risk engine and thresholds.

```bash
# Gate both sides; scan only files changed since HEAD~1
python scripts/run_hybrid_pipeline.py \
    --cdk-path examples/hybrid-demo/cdk \
    --ansible-path examples/hybrid-demo/ansible \
    --base-ref HEAD~1

# On-prem only; deploy to a Tailscale-connected node if the gate allows
python scripts/run_hybrid_pipeline.py \
    --ansible-path examples/hybrid-demo/ansible \
    --target-host 100.101.102.103 --deploy

# Read-only status
python scripts/run_hybrid_pipeline.py --query-status     # gate score/decision per target
python scripts/run_hybrid_pipeline.py --hybrid-status    # SSM nodes + compliance + Tailscale mesh
```

Key differences from the CDK-only flow:

- **No generation** — the hybrid orchestrator never calls `AIgen/`.
- **Ansible scanners** — `ansible-lint` + Checkov (`--framework ansible`) +
  a regex secret scan feed the *same* Risk Scoring Engine (severity weights and
  thresholds are unchanged). Infracost / AWS Config do not apply to playbooks.
- **Changed-file scoping** — `--base-ref` limits the Ansible scan to git-changed
  YAML files (`pipeline/git_changes.py`); a full scan is used when omitted.
- **Execution** — `ansible-playbook --syntax-check` (validate) →
  `--check --diff` (dry-run) → `ansible-playbook -i <inventory>` (deploy) over
  Tailscale, mirroring `cdk synth → diff → deploy`.
- **On-prem monitoring** — `Monitor/ssm_hybrid.py` registers private nodes as
  SSM managed instances (compliance events reuse the existing ops-loop);
  `Monitor/hybrid_dashboard.py` builds an AWS<->on-prem CloudWatch dashboard.

> UI integration for hybrid mode is intentionally deferred — the CLI is the
> source of truth and emits JSON-friendly output for the UI to consume later.

## Repository Structure

| Path | Role in pipeline |
|---|---|
| `AIgen/` | LLM generation (Bedrock/OpenRouter) + generation/eval orchestration |
| `AIgen/run_cdk_regen.py` | CDK-specific regen loop: generate → synth → gate → retry on reject |
| `Eval/` | Validation, security analysis, risk scoring, IaC gate |
| `Eval/scanners/` | Pluggable scanner adapters (Checkov, cfn-lint, Infracost, AWS Config, ansible-lint, secret-scan) |
| `pipeline/` | CDK command runner + deploy decision logic |
| `pipeline/ansible_pipeline.py` | Ansible execution: syntax-check, dry-run (`--check`), deploy + Ansible gate runner |
| `pipeline/git_changes.py` | Git changed-file discovery for scoping scans to modified files |
| `pipeline/hybrid_status.py` | Read-only on-prem visibility: SSM nodes, SSM compliance, Tailscale devices |
| `pipeline/notifier.py` | AWS SNS notifier for gate and deploy events |
| `pipeline/ssm_store.py` | SSM Parameter Store persistence for gate results (Phase 4) |
| `pipeline/eventbridge_trigger.py` | EventBridge custom event publisher (Phase 4) |
| `pipeline/lambda_handler.py` | Standalone Lambda for drift detection + rollback alerts (Phase 4) |
| `pipeline/aws_credentials.py` | Central AWS credential resolver with SSO auto-export (Phase 4) |
| `Monitor/` | Phase 4 ops-loop infrastructure |
| `Monitor/cloudwatch_publisher.py` | CloudWatch gate metrics + structured log publisher |
| `Monitor/stack_monitor.py` | 3-layer post-deploy security monitoring setup |
| `Monitor/ops_loop_stack.py` | CDK stack for Lambda, EventBridge rules, CW alarms, dashboard |
| `scripts/run_cdk_pipeline.py` | CLI pipeline: synth → gate → diff → optional deploy |
| `scripts/run_hybrid_pipeline.py` | Hybrid CLI: gate CDK + Ansible (no generation), per-target observability |
| `Monitor/ssm_hybrid.py` | SSM Hybrid Activation for on-prem nodes (managed instance registration) |
| `Monitor/hybrid_dashboard.py` | AWS<->on-prem CloudWatch dashboard (risk score + network flow) |
| `examples/hybrid-demo/` | Minimal hybrid project: one CDK stack + one Ansible playbook |
| `ui/` | Streamlit UI modules including `CDK Deploy` control tab |
| `ui_app.py` | Backward-compatible launcher that calls `ui/main.py` |
| `GeneratedCDK/` | Generated CDK app and command logs |
| `logs/gate_reports/` | Persisted gate report JSON files (one per run) |
| `logs/approvals/` | Persisted approval records with AWS ARN of approver |
| `logs/rejections/` | Persisted rejection records with top findings |
| `logs/cdk_regen/` | Per-run artifacts from CDK regen loop (prompts, code, gate reports) |
| `ExecComponent/` | Safe subprocess execution helpers |
| `Monitor/` | Phase 4 ops-loop + observability CDK stacks and runtime helpers |
| `ui/` | Streamlit operator console (modular package) |

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

Credentials are resolved automatically if you have already run `aws sso login`. The pipeline uses `pipeline/aws_credentials.py` which tries the boto3 default chain first, then automatically exports SSO tokens via the AWS CLI as a fallback — no manual env var setup needed after `aws sso login`.

For static credentials (CI/CD or IAM user):

```bash
export AWS_ACCESS_KEY_ID=<your_key>
export AWS_SECRET_ACCESS_KEY=<your_secret>
export AWS_REGION=us-east-1
```

For SSO (recommended for local dev) — just run:

```bash
aws sso login
# Pipeline auto-exports tokens from that point on
```

Optional if using OpenRouter:

```bash
export OPENROUTER_API_KEY=<your_key>
```

### 3. Generate CDK code with the regen loop

```bash
python AIgen/run_cdk_regen.py --prompt "Generate a secure AWS CDK Python app" \
  --project-dir GeneratedCDK --provider bedrock --max-attempts 2
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
| `--manual-approve` | off | Approve review-band score (21–80) |
| `--deploy` | off | Run `cdk deploy` if gate allows |
| `--bootstrap` | off | Run `cdk bootstrap` first |
| `--prompt` | — | Original CDK request (used with `--regen-on-reject`) |
| `--regen-on-reject` | off | On gate reject, invoke CDK regen loop |
| `--max-regen-attempts` | `2` | Max regen loop attempts (used with `--regen-on-reject`) |
| `--approve-run-id` | — | Approve an existing review-band report by run ID |
| `--query-status` | off | Print last gate result per stack from SSM and exit |

## Phase 4 — Ops Loop & Real-Time Monitoring

All Phase 4 components activate automatically after every pipeline run. No extra flags needed.

### SSM Parameter Store

Gate results are persisted to SSM after every evaluation:

```
/syssecops/gate/{stack_name}/latest_score
/syssecops/gate/{stack_name}/latest_decision
/syssecops/gate/{stack_name}/latest_run_id
/syssecops/gate/{stack_name}/latest_report_path
```

Query all tracked stacks:

```bash
python scripts/run_cdk_pipeline.py --query-status
```

Disable SSM: `export SSM_ENABLED=false`

### EventBridge

A `GateDecision` custom event is published to the default EventBridge bus after every gate evaluation (`source: syssecops.gate`). Disable: `export EVENTBRIDGE_ENABLED=false`

### CloudWatch Metrics + Logs

Metrics published to `SysSecOps/Gate` namespace (dimensions: `StackName` + `RunId`):
- `GateScore`, `GateDecision`, `CriticalFindings`, `HighFindings`

Full gate report written as a structured log event to `/syssecops/gate/{stack_name}/{run_id}`.

### Drift Detection + Rollback Alerts

Deploy the ops-loop Lambda stack once:

```bash
cd Monitor && cdk deploy SysSecOpsOpsLoopStack
```

This provisions EventBridge rules that fire the Lambda on AWS Config compliance drift or CloudFormation rollback, triggering SNS notifications (and optionally re-running the pipeline).

Set `RETRIGGER_MODE=auto_retrigger` + `PIPELINE_LAMBDA_ARN=<arn>` for fully automated remediation.

### Post-Deploy Stack Security Monitoring

Called automatically after every successful `cdk deploy`. Three layers:

**Layer 1 — Application Insights:** auto-discovery of EC2/Lambda/RDS/ECS resources.

**Layer 2 — CloudWatch metric alarms per resource:**
- Operational: CPU, memory, errors, throttles, storage
- Security: network packet spikes (EC2), timeout exhaustion (Lambda), connection floods (RDS), S3 4xx/5xx access errors

**Layer 3a — CloudTrail security alarms (7 CIS-aligned):**
`UnauthorizedAPICalls`, `RootAccountUsage`, `IAMPolicyChanges`, `SecurityGroupChanges`, `S3BucketPolicyChanges`, `CloudTrailChanges`, `ConsoleAuthFailures`

Requires CloudTrail → CloudWatch Logs integration on log group `/aws/cloudtrail/syssecops`.

**Layer 3b — VPC flow log alarms:**
`VPCFlowRejects` (port scan indicator) + `SSHRDPFromInternet`. Auto-detected; skips if no VPCs or no flow logs.

### CloudWatch Dashboard

Dashboard `SysSecOpsGate` is provisioned by `SysSecOpsOpsLoopStack`:
```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=SysSecOpsGate
```

Shows gate score trend, findings counts, and alarm status widgets.

## Streamlit UI

Run (use the project virtualenv — system Python lacks Streamlit):

```bash
.venv/bin/python -m streamlit run ui/main.py
# or the backward-compatible shim:
.venv/bin/python -m streamlit run ui_app.py
```

The console drives the full pipeline through six tabs — **🔑 Login**, **🚀 Pipeline**,
**📂 Results**, **📡 Monitor**, **🛡️ Security**, **⚙️ Settings**. The Pipeline tab has four
sub-tabs (Generate + Gate → Review & Edit → Decision → Deploy) and supports:

- generating CDK code from a natural-language prompt
- editing `GeneratedCDK/app.py` and re-running `cdk synth` + the full gate
- enforcing deploy gating with optional manual approval for the review band (21–80)
- writing approval/rejection records and (when `SNS_TOPIC_ARN` is set) SNS notifications
- live monitoring of SSM gate state and CloudWatch alarms

Credentials entered in the Login tab are saved to `~/.aws/` and `.env`, then injected into
subprocesses as environment variables. See [`ui/README.md`](ui/README.md) for details.

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
- `CRITICAL × 20`, `HIGH × 10`, `MEDIUM × 5`, `LOW × 1`
- `cost_delta_usd > $10`: +5 pts | `> $50`: +10 pts
- `aws_config_violations × 5` pts

**Decision thresholds:**
- `0–20`: `pass` — auto deploy allowed
- `21–80`: `review` — manual approval required
- `> 80`: `reject` — blocked

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

- [`THESIS_REPORT.md`](THESIS_REPORT.md) — comprehensive thesis report (architecture, methodology, evaluation)
- [`AIgen/README.md`](AIgen/README.md) — generation providers and the CDK regen loop
- [`Eval/README.md`](Eval/README.md) — gate scoring, scanner adapters, report structure
- [`pipeline/README.md`](pipeline/README.md) — CDK orchestration + Phase 4 governance
- [`Monitor/README.md`](Monitor/README.md) — ops loop, alarms, dashboards, 3-layer monitoring
- [`ExecComponent/README.md`](ExecComponent/README.md) — subprocess execution helpers
- [`scripts/README.md`](scripts/README.md) — pipeline CLI flags and return codes
- [`ui/README.md`](ui/README.md) — Streamlit operator console
- [`GeneratedCDK/README.md`](GeneratedCDK/README.md) — the CDK deployment target
- [`PHASE4_REPORT.md`](PHASE4_REPORT.md) — detailed Phase 4 implementation report
- [`CDK-ONLY-NEXT-STEPS.md`](CDK-ONLY-NEXT-STEPS.md) — implementation roadmap (Phases 1–4)
