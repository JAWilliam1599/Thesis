# scripts — Pipeline CLI Entry Point

## Purpose

`scripts/` holds the command-line entry point that orchestrates the full CDK pipeline:
`bootstrap → synth → gate → diff → deploy`, with approval workflows, rejection records, an
optional auto-regen loop, and Phase 4 observability (SSM, EventBridge, SNS, CloudWatch).

## Files

| File | Role |
|---|---|
| `run_cdk_pipeline.py` | CDK-only CLI orchestrator that wires together `pipeline/`, `Eval/`, `Monitor/`, and `AIgen/` (includes the optional code-generation / regen loop) |
| `run_hybrid_pipeline.py` | Hybrid CLI orchestrator: gates and deploys a bring-your-own **CDK + on-prem Ansible** project with the *same* risk engine — **no code generation** |

```mermaid
flowchart LR
    CLI[run_cdk_pipeline.py] --> CP[pipeline.cdk_pipeline]
    CLI --> AC[pipeline.aws_credentials]
    CLI --> N[pipeline.notifier]
    CLI --> S[pipeline.ssm_store]
    CLI --> EB[pipeline.eventbridge_trigger]
    CLI --> CWP[Monitor.cloudwatch_publisher]
    CLI --> SM[Monitor.stack_monitor]
    CLI -.on reject.-> RG[AIgen.run_cdk_regen]
```

## Usage

```bash
# Full run — all scanners auto-enabled
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK

# Fast run — skip external scanners
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --no-checkov --no-cfn-lint

# Manual-approve a review-band score and deploy
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --manual-approve --deploy

# Approve an existing review-band gate report by run ID, then deploy
python scripts/run_cdk_pipeline.py --approve-run-id cdk_20260617T122700Z --deploy

# Auto-regenerate on reject
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK \
  --regen-on-reject --max-regen-attempts 3 \
  --prompt "Create an S3 bucket with versioning and encryption"

# Print last gate result per stack from SSM and exit
python scripts/run_cdk_pipeline.py --query-status
```

## Public Functions

| Function | Purpose |
|---|---|
| `parse_args()` | Parses all CLI flags |
| `main()` | Main pipeline orchestrator |
| `query_status_main()` | Read-only: print last gate result per stack from SSM |
| `approve_and_deploy_main(args, project_dir, env)` | Approve existing review-band report + optional deploy |

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--project-dir` | `GeneratedCDK` | CDK project directory |
| `--run-id` | auto | Override gate-report filename |
| `--approve-run-id RUN_ID` | — | Skip synth+gate; approve an existing review-band report |
| `--cost-delta-usd` | auto (Infracost) | Override monthly cost delta (USD) |
| `--aws-config-violations` | auto (boto3) | Override AWS Config violation count |
| `--no-infracost` | off | Skip Infracost |
| `--no-aws-config` | off | Skip AWS Config fetch |
| `--no-checkov` | off | Skip Checkov |
| `--no-cfn-lint` | off | Skip cfn-lint |
| `--manual-approve` | off | Approve review band (21–80) for deploy |
| `--deploy` | off | Run `cdk deploy` if the gate allows |
| `--bootstrap` | off | Run `cdk bootstrap` first |
| `--prompt` | — | Original request (used with `--regen-on-reject`) |
| `--regen-on-reject` | off | On reject, invoke the CDK regen loop |
| `--max-regen-attempts` | `2` | Max regen attempts |
| `--query-status` | off | Print last gate result per stack from SSM and exit |
| `--log-file` | auto | Override log file path |
| `--verbose` | off | Also print log output to stderr |

## Return Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Project directory not found |
| `3` | Gate report not found (`--approve-run-id`) |
| `9` | Bootstrap failed |
| `10` | Synth failed |
| `11` | Diff failed |
| `12` | Deploy failed |
| `21` | Review required (not approved) |
| `22` | Rejected (regen attempted or no prompt provided) |

These codes are surfaced verbatim by the Streamlit UI via `ui/config.py::RETURN_CODE_MEANING`.

## Hybrid Pipeline (`run_hybrid_pipeline.py`)

The hybrid entry point runs the identical `gate → risk-score → deploy → observability`
workflow over **both sides of a hybrid project the user already wrote** — an AWS CDK app and
an on-prem Ansible project — with **no code-generation step**. Each branch is gated
independently with the same severity weights and thresholds; a combined report is written to
`logs/hybrid_<run_id>.json`. Infracost / AWS Config / ML-risk apply to the CDK branch only;
`ansible-lint` + Checkov (`--framework ansible`) + a regex secret scan feed the Ansible branch.

```bash
# Gate both sides; scope the Ansible scan to files changed since HEAD~1
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

### Key CLI flags

| Flag | Default | Description |
|---|---|---|
| `--cdk-path` | — | CDK app directory (omit to skip the CDK branch) |
| `--ansible-path` | — | Ansible project directory (omit to skip the Ansible branch) |
| `--base-ref` | scan all | Git ref for changed-file scoping of the Ansible scan (e.g. `HEAD~1`) |
| `--playbook` / `--inventory` | auto-detect | Playbook / inventory file relative to the Ansible path |
| `--target-host` | — | Tailscale host/IP used as an inline inventory when no inventory file is given |
| `--manual-approve` | off | Approve review-band (21–80) decisions for deploy |
| `--deploy` | off | Deploy each branch the gate allows |
| `--bootstrap` | off | Run `cdk bootstrap` before synth (CDK branch) |
| `--no-checkov` / `--no-cfn-lint` / `--no-infracost` / `--no-ml-risk` / `--no-aws-config` | off | Skip scanners on the CDK branch (Checkov applies to both) |
| `--no-ansible-lint` / `--no-secret-scan` | off | Skip scanners on the Ansible branch |
| `--pass-max` / `--review-max` | `20` / `80` | Override decision thresholds |
| `--query-status` | off | Print last gate result per target from SSM and exit |
| `--hybrid-status` | off | Print on-prem mesh status (SSM nodes, compliance, Tailscale) and exit |
| `--run-id` / `--log-file` / `--verbose` | auto | Run-ID / log-path overrides and stderr echo |

### Return codes

| Code | Meaning |
|---|---|
| `0` | All attempted branches passed / deployed successfully |
| `1` | At least one branch errored, was rejected, or failed to deploy |
| `2` | No target provided (`--cdk-path` / `--ansible-path` / `--query-status` all absent) |

## Side Effects

- **Writes:** `logs/cdk_pipeline_<run_id>.log`, gate reports, approval/rejection records.
- **Phase 4:** persists to SSM, publishes an EventBridge `GateDecision` event, emits
  CloudWatch metrics + structured logs, and (on successful deploy) attaches 3-layer stack
  monitoring. SNS notifications fire when `SNS_TOPIC_ARN` is set.

See [`../README.md`](../README.md) and [`../THESIS_REPORT.md`](../THESIS_REPORT.md).
