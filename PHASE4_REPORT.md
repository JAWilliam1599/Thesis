# Phase 4 Report — SysSecOps Ops Loop & Real-Time Monitoring

**Date:** 2026-06-16  
**Scope:** Post-gate observability, drift detection, security monitoring, credential management

---

## Overview

Phase 4 extends the SysSecOps CDK pipeline with a full operational loop: after every gate evaluation, results are persisted, events are emitted, and security monitoring is attached to deployed stacks. The loop is self-healing — AWS Config drift or CloudFormation rollbacks trigger automatic notifications and optional re-evaluation.

```
cdk synth → IaC Gate → [ SSM | EventBridge | CloudWatch Metrics+Logs ]
                ↓
           cdk deploy → Stack Monitoring Setup (3-layer security alarms)
                ↓
           Drift / Rollback → EventBridge → Lambda → SNS notification
```

---

## 4A — Gate Result Persistence (SSM Parameter Store)

**File:** `pipeline/ssm_store.py`

Writes gate evaluation results to SSM after every pipeline run, providing a queryable audit trail independent of the local filesystem.

### SSM Parameter Schema

| Parameter path | Value | Example |
|---|---|---|
| `/syssecops/gate/{stack}/latest_score` | Numeric risk score (string) | `"35"` |
| `/syssecops/gate/{stack}/latest_decision` | `pass` / `review` / `reject` | `"review"` |
| `/syssecops/gate/{stack}/latest_run_id` | Pipeline run ID | `"cdk_20260616T131322Z"` |
| `/syssecops/gate/{stack}/latest_report_path` | Local report path or `"none"` | `"/home/.../gate_cdk_...json"` |

### Public API

| Function | Purpose |
|---|---|
| `write_gate_result(stack, run_id, score, decision, report_path)` | Upserts 4 SSM parameters after gate evaluation |
| `read_gate_result(stack) → dict\|None` | Reads current state for a stack |
| `list_monitored_stacks() → list[str]` | Lists all stacks with SSM records |

### Configuration

| Env var | Default | Effect |
|---|---|---|
| `SSM_ENABLED` | `true` | Set `false` to skip all SSM operations |
| `AWS_DEFAULT_REGION` | `us-east-1` | SSM region |

### CLI Integration

```bash
python scripts/run_cdk_pipeline.py --query-status
# Prints a table: STACK | SCORE | DECISION | RUN_ID for all tracked stacks
```

### Bugs Fixed

- **Empty string rejection:** `report_path or ""` caused SSM `ValidationException` (length ≥ 1 required). Fixed to `report_path if report_path else "none"`.

---

## 4B — Event Bus Integration (EventBridge + Lambda)

### EventBridge Publisher

**File:** `pipeline/eventbridge_trigger.py`

Publishes a `GateDecision` custom event to the EventBridge default bus after every gate evaluation.

| Field | Value |
|---|---|
| Source | `syssecops.gate` |
| DetailType | `GateDecision` |
| Payload | `run_id`, `stack_name`, `decision`, `score`, `timestamp` |

| Env var | Default | Effect |
|---|---|---|
| `EVENTBRIDGE_ENABLED` | `true` | Set `false` to skip publishing |

### Lambda Handler

**File:** `pipeline/lambda_handler.py`

Standalone Lambda (stdlib + boto3 only, no project imports) that handles two EventBridge patterns:

**Pattern 1 — AWS Config compliance drift**
- Trigger: `aws.config` source + `Config Rules Compliance Change` detail type
- Action: reads SSM to check last gate decision for that stack
- If last decision was `pass` and now `NON_COMPLIANT` → publishes `drift_detected` SNS
- If `RETRIGGER_MODE=auto_retrigger` → invokes `PIPELINE_LAMBDA_ARN` to re-run gate

**Pattern 2 — CloudFormation rollback**
- Trigger: `aws.cloudformation` source + `CloudFormation Stack Status Change`
- On `ROLLBACK_COMPLETE`, `UPDATE_ROLLBACK_COMPLETE`, `CREATE_FAILED`, `UPDATE_FAILED`, `DELETE_FAILED` → publishes `stack_rollback` SNS

| Env var | Required | Description |
|---|---|---|
| `SNS_TOPIC_ARN` | Yes (for notifications) | Notification target |
| `RETRIGGER_MODE` | No | `notify_only` (default) or `auto_retrigger` |
| `PIPELINE_LAMBDA_ARN` | Only for `auto_retrigger` | Lambda to invoke for pipeline re-run |

### CDK Ops-Loop Stack

**File:** `Monitor/ops_loop_stack.py`  
**Class:** `SysSecOpsOpsLoopStack`

Provisions all Lambda infrastructure via CDK:

- Lambda function pointing to `pipeline/lambda_handler.py`
- IAM execution role with least-privilege (SSM read, SNS publish, Lambda invoke, CloudWatch put)
- EventBridge Rule 1: Config compliance → Lambda
- EventBridge Rule 2: CFN rollback statuses → Lambda
- CloudWatch Alarm: `GateRejectAlarm` (GateDecision = 2 for ≥ 1 period)
- CloudWatch Alarm: `HighCriticalFindingsAlarm` (CriticalFindings + HighFindings ≥ 3)
- CloudWatch Dashboard: `SysSecOpsGate` (score trend + findings counts + alarm widgets)

**Deploy:**
```bash
cd Monitor && cdk deploy SysSecOpsOpsLoopStack
```

**Output:** `SysSecOpsOpsLoopFunctionArn` (use as `PIPELINE_LAMBDA_ARN` for auto-retrigger)

---

## 4C — Metrics and Structured Logs (CloudWatch)

### Gate Metrics Publisher

**File:** `Monitor/cloudwatch_publisher.py`

Publishes per-run metrics immediately after gate evaluation.

**Namespace:** `SysSecOps/Gate`  
**Dimensions:** `StackName` + `RunId`

| Metric | Statistic | Description |
|---|---|---|
| `GateScore` | Maximum | Numeric risk score (0–∞) |
| `GateDecision` | Maximum | 0=pass, 1=review, 2=reject |
| `CriticalFindings` | Sum | Count of critical-severity findings |
| `HighFindings` | Sum | Count of high-severity findings |

**Structured Log Events:**

| Log group | `/syssecops/gate/{stack_name}` |
|---|---|
| Log stream | `{run_id}` |
| Content | Full gate report as JSON (all findings, score breakdown, inputs) |

---

## 4D — Stack Monitoring (Three-Layer Security)

**File:** `Monitor/stack_monitor.py`  
**Called:** After every successful `cdk deploy`

### Layer 1 — CloudWatch Application Insights

Registers the deployed stack as an Application Insights application for auto-discovery and anomaly detection.

- Creates a tag-based resource group (`TAG_FILTERS_1_0`) matching all resources with `aws:cloudformation:stack-name={stack_name}`
- Registers the group as an Application Insights application with `AutoConfigEnabled=True`
- Idempotent: skips gracefully if the group/application already exists

> Note: `CLOUDFORMATION_STACK_1_0` query type is rejected for IAM users; `TAG_FILTERS_1_0` is used instead.

### Layer 2 — Explicit CloudWatch Metric Alarms (per stack template)

Parses the CDK-synthesised CloudFormation template and creates targeted alarms for each resource.

#### Operational alarms

| Resource | Metric | Threshold | Purpose |
|---|---|---|---|
| `AWS::EC2::Instance` | `CPUUtilization` | ≥ 80% | High load |
| `AWS::EC2::Instance` | `StatusCheckFailed` | ≥ 1 | Instance health |
| `AWS::Lambda::Function` | `Errors` | ≥ 1 | Runtime failures |
| `AWS::Lambda::Function` | `Throttles` | ≥ 1 | Rate limiting |
| `AWS::RDS::DBInstance` | `FreeStorageSpace` | ≤ 10 GB | Disk exhaustion |
| `AWS::RDS::DBInstance` | `CPUUtilization` | ≥ 80% | High load |
| `AWS::ECS::Service` | `CPUUtilization` | ≥ 80% | Container load |
| `AWS::ECS::Service` | `MemoryUtilization` | ≥ 80% | Memory pressure |

#### Security alarms (new in Phase 4)

| Resource | Metric | Threshold | Security signal |
|---|---|---|---|
| `AWS::EC2::Instance` | `NetworkPacketsIn` | ≥ 1M / 5min | Port scan / DDoS indicator |
| `AWS::Lambda::Function` | `Duration` | ≥ 12 min (80% of 15-min max) | Timeout exhaustion attack |
| `AWS::Lambda::Function` | `ConcurrentExecutions` | ≥ 50 | Resource abuse |
| `AWS::RDS::DBInstance` | `DatabaseConnections` | ≥ 100 | Connection flood / brute force |

#### S3 security alarms (separate function — different dimension format)

For each `AWS::S3::Bucket` in the template:
1. Resolves physical bucket name via `cloudformation.describe_stack_resource`
2. Enables CloudWatch request metrics (`put_bucket_metrics_configuration`)
3. Creates alarms on `AWS/S3` namespace with `BucketName` + `FilterId=EntireBucket` dimensions:

| Metric | Threshold | Security signal |
|---|---|---|
| `4xxErrors` | ≥ 10 / 5min | Unauthorized / forbidden access attempts |
| `5xxErrors` | ≥ 5 / 5min | Server errors / possible injection |

### Layer 3a — CloudTrail Security Alarms (account-wide, CIS-aligned)

Auto-detects the CloudTrail → CloudWatch Logs integration by checking for `/aws/cloudtrail/syssecops`. Creates 7 metric filter + alarm pairs.

**Namespace:** `SysSecOps/CloudTrailSecurity`  
**Period:** 300s (5 minutes), EvaluationPeriods=1

| Alarm | Threshold | Filter |
|---|---|---|
| `UnauthorizedAPICalls` | ≥ 5 / 5min | `errorCode = AccessDenied \|\| UnauthorizedAccess` |
| `RootAccountUsage` | ≥ 1 / 5min | Root account activity, non-service events |
| `IAMPolicyChanges` | ≥ 1 / 5min | Create/Delete/Attach/Detach policy events |
| `SecurityGroupChanges` | ≥ 1 / 5min | Authorize/Revoke ingress/egress, create/delete SG |
| `S3BucketPolicyChanges` | ≥ 1 / 5min | PutBucketPolicy, DeleteBucketPolicy, PutBucketAcl |
| `CloudTrailChanges` | ≥ 1 / 5min | StopLogging, DeleteTrail, UpdateTrail |
| `ConsoleAuthFailures` | ≥ 3 / 5min | Console login with `Failed authentication` |

All alarms fire to `SNS_TOPIC_ARN`. Metric filters write to `SysSecOps/CloudTrailSecurity` namespace.

> Tested against trail: `arn:aws:logs:us-east-1:926208928139:log-group:/aws/cloudtrail/syssecops`

### Layer 3b — VPC Flow Log Alarms (per VPC in template)

Auto-detects `AWS::EC2::VPC` resources, resolves physical VPC IDs, queries `ec2.describe_flow_logs` for CloudWatch-destined flow logs, then creates:

**Namespace:** `SysSecOps/VPCFlowLogs`

| Alarm | Threshold | Filter |
|---|---|---|
| `VPCFlowRejects` | ≥ 100 / 5min | `action=REJECT` in flow log records |
| `SSHRDPFromInternet` | ≥ 1 / 5min | Port 22 or 3389, protocol TCP, action ACCEPT |

Silently skips if: no VPCs in template, no flow logs configured, or flow logs not destined to CloudWatch Logs.

---

## 4E — Credential Management

**File:** `pipeline/aws_credentials.py`

Central credential resolver used by all pipeline modules. Eliminates per-module boto3 client construction and provides a shared session with automatic SSO support.

### Resolution Order

1. **Module cache** — process-lifetime cache, short-circuits all checks
2. **boto3 default chain** — env vars, `~/.aws/credentials`, SSO cache, instance metadata
3. **CLI auto-export** — if chain fails, runs `aws configure export-credentials --format env-no-export` (no profile first, then each SSO profile) and retries. This resolves the SSO gap where `aws sts get-caller-identity` works but venv boto3 cannot find the SSO token file.

### Public API

| Function | Purpose |
|---|---|
| `get_session(profile_name, force_refresh)` | Returns cached `boto3.Session` or `None` |
| `get_identity(session)` | Returns `{UserId, Account, Arn}` or `None` |
| `list_sso_profiles()` | Lists SSO-configured profiles from `~/.aws/config` |
| `login_sso(profile_name)` | Runs `aws sso login --profile` and auto-exports |
| `export_sso_credentials(profile_name)` | Exports tokens into `os.environ`, invalidates cache |
| `invalidate_cache()` | Clears session cache (call after token refresh) |

### Integration Pattern

All four Phase 4 service modules (`ssm_store`, `eventbridge_trigger`, `cloudwatch_publisher`, `stack_monitor`) call `get_session().client(service)` with a direct boto3 fallback. The pre-flight check in `scripts/run_cdk_pipeline.py` uses `get_session() is None` to skip observability silently when no credentials are available.

---

## Pipeline Integration Points

### `scripts/run_cdk_pipeline.py` — changes

| Addition | Where called | Purpose |
|---|---|---|
| `_emit_gate_observability(gate_report, stack_name)` | After every gate evaluation | Fires SSM write + EventBridge publish + CW metrics + CW log |
| `clear_cdk_out(project_dir)` | Before every `cdk synth` | Prevents stale template accumulation |
| `extract_stack_name(gate_report)` | After gate | Derives stack name from template filename |
| `setup_stack_monitoring(stack_name, cdk_out_dir)` | After successful deploy | Attaches all 3 monitoring layers |
| `query_status_main()` | `--query-status` flag | Prints SSM table of all tracked stacks |

### `AIgen/run_cdk_regen.py` — changes

- `clear_cdk_out(project_dir)` called before each `cdk synth` attempt in the regen loop
- Prompt enforced to `EXACTLY ONE Stack class` (prevents multi-stack generation that inflated template counts)

---

## AWS Resources Created

| Resource | Name / Path | Service |
|---|---|---|
| SSM Parameters | `/syssecops/gate/{stack}/latest_*` (4 per stack) | SSM Parameter Store |
| EventBridge events | `syssecops.gate / GateDecision` on default bus | EventBridge |
| Lambda function | `SysSecOpsOpsLoopStack-OpsLoopFn-*` | Lambda |
| EventBridge rules | Config compliance + CFN rollback → Lambda | EventBridge |
| CloudWatch alarms | `syssecops-{stack}-*` (resource + security) | CloudWatch |
| CloudWatch alarms | `syssecops-{stack}-{CIS alarm name}` × 7 | CloudWatch |
| Metric filters | 7 filters on `/aws/cloudtrail/syssecops` | CloudWatch Logs |
| CloudWatch metrics | `SysSecOps/Gate` namespace | CloudWatch |
| CloudWatch metrics | `SysSecOps/CloudTrailSecurity` namespace | CloudWatch |
| CloudWatch metrics | `SysSecOps/VPCFlowLogs` namespace | CloudWatch |
| CloudWatch Logs | `/syssecops/gate/{stack_name}` (one stream per run) | CloudWatch Logs |
| Dashboard | `SysSecOpsGate` | CloudWatch |
| Application Insights app | `syssecops-{stack_name}` resource group | Application Insights |

---

## Bugs Found and Fixed During Phase 4

| Bug | Root Cause | Fix |
|---|---|---|
| `ValidationException` on SSM write | `report_path or ""` passes empty string; SSM requires length ≥ 1 | Changed to `report_path if report_path else "none"` |
| Application Insights `ResourceNotFoundException` | `CLOUDFORMATION_STACK_1_0` query type rejected for IAM users; stack name used instead of ARN | Switched to `TAG_FILTERS_1_0` using `aws:cloudformation:stack-name` tag |
| `"Unable to locate credentials"` ×4 per pipeline run | boto3 in venv cannot resolve SSO tokens from `~/.aws/sso/cache/` automatically | `get_session()` now auto-runs `aws configure export-credentials` as fallback |
| Observability skipped even after SSO login | Credential pre-flight checked `_has_aws_credentials()` with inline sts call; cache not invalidated after credential export | Replaced with `get_session()` from central `aws_credentials.py`; cache invalidated by `export_sso_credentials()` |
| 11 templates scanned by gate | `cdk.out/` never cleaned between runs; stale templates from prior stacks accumulated | `clear_cdk_out()` called before every `cdk synth` in all entry points |
| Checkov scanning stale templates | `checkov -d cdk_out_dir` scanned entire directory | Changed to `checkov --file <path>` per template using the same list as the gate |

---

## Verification Checklist

```bash
# SSM — check gate result was persisted
aws ssm get-parameters-by-path --path /syssecops/gate/S3BucketStack/ --query 'Parameters[].{Name:Name,Value:Value}'

# CloudWatch metrics — check gate metrics landed
aws cloudwatch list-metrics --namespace SysSecOps/Gate

# CloudWatch alarms — resource + security alarms
aws cloudwatch describe-alarms --alarm-name-prefix syssecops-S3BucketStack \
  --query 'MetricAlarms[].{Name:AlarmName,State:StateValue}' --output table

# CloudTrail metric filters
aws logs describe-metric-filters --log-group-name /aws/cloudtrail/syssecops \
  --query 'metricFilters[].filterName'

# Application Insights
aws application-insights list-applications

# Resource groups
aws resource-groups list-groups

# Force-test an alarm (bypass 5-min CloudTrail delivery wait)
aws cloudwatch set-alarm-state \
  --alarm-name syssecops-S3BucketStack-UnauthorizedAPICalls \
  --state-value ALARM \
  --state-reason "manual test"
```

---

## Architecture Diagram

```
CDK Pipeline Run
│
├── cdk synth (cdk.out/ cleared first)
│
├── IaC Gate (Eval/)
│   ├── checkov --file per-template
│   ├── cfn-lint
│   ├── infracost
│   └── heuristic analyzer
│       └── Score → decision (pass/review/reject)
│
├── _emit_gate_observability()
│   ├── SSM: /syssecops/gate/{stack}/latest_*
│   ├── EventBridge: syssecops.gate / GateDecision
│   ├── CloudWatch Metrics: SysSecOps/Gate
│   └── CloudWatch Logs: /syssecops/gate/{stack}/{run_id}
│
└── cdk deploy (if allowed)
    │
    └── setup_stack_monitoring()
        ├── Layer 1: Application Insights (tag-based resource group)
        ├── Layer 2: Explicit alarms
        │   ├── EC2/Lambda/RDS/ECS operational + security metrics
        │   └── S3 4xxErrors / 5xxErrors (request metrics enabled)
        ├── Layer 3a: CloudTrail metric filter alarms (×7 CIS)
        └── Layer 3b: VPC flow log alarms (REJECT + SSH/RDP)

EventBridge Bus (default)
│
├── AWS Config compliance change
│   └── Lambda (ops_loop) → drift_detected SNS
│
└── CFN stack status change (rollback)
    └── Lambda (ops_loop) → stack_rollback SNS
```
