# Generate + Eval + Security Gate End-to-End Test

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/run_generation_and_eval.py#1-1), lines 1 to 80

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/openrouter_codegen.py#1-1), lines 1 to 60

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/run_generation_and_eval.py#80-80), lines 80 to 160

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/bedrock_codegen.py#1-1), lines 1 to 100

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/run_generation_and_eval.py#160-160), lines 160 to 260

Searched for text `OPENROUTER_API_KEY|BEDROCK|AWS_PROFILE|aws_region` (`**/AIgen/*.py`), 20 results

Read [](file:///home/astia/Documents/Thesis/Thesis/AIgen/run_generation_and_eval.py#260-260), lines 260 to 360

Searched for text `prepare_generated_cdk_project`, 3 results

Searched for text `OPENROUTER_API_KEY` (`**/.env*`), no results

Read [](file:///home/astia/Documents/Thesis/Thesis/ui/cdk_control.py#78-78), lines 78 to 115

Searched for text `OPENROUTER_API_KEY` (`**/.env`), no results

Read [](file:///home/astia/Documents/Thesis/Thesis/GeneratedCDK/app.py#1-1), lines 1 to 30

I have enough context. Here are the full step-by-step instructions:

---

## End-to-End CLI Test: Generate → Eval → Security Gate

### Prerequisites — check these first

```bash
# 1. Confirm venv is active (all commands below assume the venv)
source .venv/bin/activate   # or: . .venv/bin/activate.fish

# 2. Confirm AWS credentials are set (needed for Bedrock or CDK synth)
aws sts get-caller-identity

# 3. Confirm CDK CLI is on PATH
cdk --version
```

If you're using **OpenRouter** instead of Bedrock, export your key:
```bash
export OPENROUTER_API_KEY="sk-or-..."
```

---

### Step 1 — Generate code + evaluate (AIgen → Eval)

Run from the AIgen directory. The script must be invoked from there because it has relative imports:

```bash
cd AIgen

# --- Option A: OpenRouter (no AWS Bedrock needed) ---
python run_generation_and_eval.py \
  --provider openrouter \
  --prompt "Create an AWS CDK app that provisions a VPC with a public subnet, an EC2 t3.micro instance with SSH open from 0.0.0.0/0, and an unencrypted EBS volume" \
  --deployment-context public \
  --max-regen 1 \
  -v

# --- Option B: Bedrock ---
python run_generation_and_eval.py \
  --provider bedrock \
  --prompt "Create an AWS CDK app that provisions a VPC, EC2 t3.micro with SSH from anywhere, and an unencrypted EBS volume" \
  --region us-east-1 \
  --deployment-context public \
  -v
```

**What this does:** Generates CDK Python code → evaluates it with bandit/quickval → saves pass/fail snapshots under `ExecCode/run_<timestamp>/`. Generated code lands at generated_code.py.

```bash
cd ..   # back to repo root
```

---

### Step 2 — Copy generated code into GeneratedCDK

The CDK pipeline reads from app.py. Copy the output there:

```bash
cp ExecCode/generated_code.py GeneratedCDK/app.py
```

Or use the last passed snapshot if generation had retries:
```bash
cp ExecCode/run_*/passed/passed_attempt_*.py GeneratedCDK/app.py
```

---

### Step 3 — Run the CDK pipeline with the security gate

```bash
# Fast test — skip external scanners to just test the gate flow
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --no-checkov --no-cfn-lint

# Full test — run with real checkov + cfn-lint
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK

# With optional cost/config signals
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --cost-delta-usd 25.0 \
  --aws-config-violations 2
```

**JSON output per stage:**
```
synth   → cdk synth result + return code
gate    → score, decision, findings[], scanner_status
diff    → cdk diff result
decision → allowed: true/false + reason
```

**Expected exit codes:**
| Code | Meaning |
|------|---------|
| `0` | Passed (no `--deploy` flag) |
| `10` | `cdk synth` failed |
| `21` | Gate says **review** — pass `--manual-approve` to continue |
| `22` | Gate **rejected** — score > 60, fix the template |

---

### Step 4 — Test the reject path (unsafe template)

The prompt above (SSH from anywhere + unencrypted EBS) should score > 60. Confirm:

```bash
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK 2>&1 | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    try:
        d = json.loads(line)
        if d.get('stage') in ('gate', 'decision'):
            print(json.dumps(d, indent=2))
    except: pass
"
```

Look for `"decision": "reject"` and `"score": >60` in the gate block.

---

### Step 5 — Test the manual-approve path (score 21–60)

Use a less dangerous prompt to land in the review band, then approve:

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --cost-delta-usd 15.0 \
  --manual-approve
# exit 0 if score ≤ 60, exit 22 if still a reject
```

---

### Step 6 — (Optional) Deploy

Only run this if you have real AWS credentials and want actual provisioning:

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --deploy
```

This is blocked automatically when the gate decision is `reject`.

---

### Quick reference — single-command smoke test

```bash
source .venv/bin/activate
python scripts/run_cdk_pipeline.py --project-dir GeneratedCDK --no-checkov --no-cfn-lint | python3 -m json.tool
```

This runs synth → heuristic gate → diff and prints formatted JSON for every stage. No AWS deploy happens without `--deploy`.


# Test 2: 

Run in Terminal

The terminal tool is disabled — I can only provide the commands for you to run. Here's the complete sequence:

---

### 1. Activate venv + check prerequisites

```bash
source .venv/bin/activate.fish   # fish shell
aws sts get-caller-identity       # confirm AWS creds
cdk --version                     # confirm CDK CLI
```

---

### 2. Smoke test — fast (no external scanners)

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --no-checkov --no-cfn-lint \
  2>&1 | python3 -m json.tool
```

Expected: JSON blocks for stages `synth`, `gate`, `gate_report`, `diff`, `decision`. Gate report file appears at `logs/gate_reports/gate_cdk_<timestamp>.json`.

---

### 3. Full scanner run (checkov + cfn-lint + infracost + AWS Config)

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  2>&1 | python3 -m json.tool
```

- `python3 -m json.tool` pretty-prints the JSON output from each stage for easier reading.

---

### 4. Verify reject path — filter just gate + decision output

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --no-checkov --no-cfn-lint \
2>&1 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        if d.get('stage') in ('gate', 'decision'):
            print(json.dumps(d, indent=2))
    except: pass
"
```

The `gate` block should show:
- `scanner_status.infracost` — `ok` or `not_installed`
- `scanner_status.aws_config` — `ok`, `no_credentials`, or `not_configured`
- `cost_analysis` and `config_analysis` objects
- `report_path` pointing to `logs/gate_reports/gate_cdk_<timestamp>.json`

---

### 5. Test cost override (force review band)

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --cost-delta-usd 15.0 \
  --aws-config-violations 3 \
  --no-checkov --no-cfn-lint
# exit 21 = review required
```

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --cost-delta-usd 15.0 \
  --aws-config-violations 3 \
  --no-checkov --no-cfn-lint \
  --manual-approve
# exit 0 = approved and allowed (no --deploy = no actual deploy)
```

---

### 6. Test reject path (score > 60)

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --cost-delta-usd 55.0 \
  --aws-config-violations 5 \
  --no-checkov --no-cfn-lint
echo "exit: $status"   # fish: should be 22
```

---

### 7. Confirm report persisted

```bash
ls -lh logs/gate_reports/
cat logs/gate_reports/$(ls -t logs/gate_reports/ | head -1) | python3 -m json.tool | head -40
```

Look for `decision`, `score`, `cost_analysis`, `config_analysis`, `scanner_warnings` in the JSON.

---

### Expected exit code reference

| Exit | Meaning |
|------|---------|
| `0` | Gate passed (or review + `--manual-approve`) |
| `10` | `cdk synth` failed |
| `21` | Gate: review required (pass `--manual-approve`) |
| `22` | Gate: rejected — score > 60 |

# Test 3:

Here are the step-by-step tests for Phase 3, in order from unit-level to integration:

---

## Step 1 — Verify notifier factory (no AWS needed)

```bash
cd /home/astia/Documents/Thesis/Thesis
python -c "
from pipeline.notifier import get_notifier
# Without SNS_TOPIC_ARN → must return None
assert get_notifier() is None, 'FAIL: expected None'
print('PASS: no SNS_TOPIC_ARN → None')

# With SNS_TOPIC_ARN → must return SNSNotifier
import os; os.environ['SNS_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:000000000000:test'
import importlib, pipeline.notifier as m; importlib.reload(m)
assert m.get_notifier() is not None, 'FAIL: expected SNSNotifier'
print('PASS: SNS_TOPIC_ARN set → SNSNotifier returned')
"
```

---

## Step 2 — Verify write_rejection_record writes correct JSON

```bash
python -c "
import json, tempfile
from pathlib import Path
from pipeline.cdk_pipeline import write_rejection_record

gate = {
    'decision': 'reject', 'score': 80, 'run_id': 'cdk_test001',
    'report_path': '/tmp/gate_cdk_test001.json',
    'findings': [
        {'severity': 'critical', 'source': 'checkov', 'message': 'SSH open', 'resource_id': 'SG', 'template': 'Stack.json'},
    ]
}
with tempfile.TemporaryDirectory() as tmp:
    path = write_rejection_record('cdk_test001', gate, log_dir=Path(tmp))
    record = json.loads(Path(path).read_text())
    assert record['run_id'] == 'cdk_test001'
    assert record['gate_decision'] == 'reject'
    assert record['gate_score'] == 80
    assert len(record['top_findings']) == 1
    assert 'rejected_at' in record
    assert 'rejector_arn' in record       # may be null without real AWS creds
    print('PASS: rejection record fields OK')
    print('  rejector_arn:', record['rejector_arn'])
"
```

---

## Step 3 — Verify write_approval now includes AWS ARN fields

```bash
python -c "
import json, tempfile
from pathlib import Path
from pipeline.cdk_pipeline import write_approval

gate = {'decision': 'review', 'score': 35, 'run_id': 'cdk_test002', 'report_path': None}
with tempfile.TemporaryDirectory() as tmp:
    path = write_approval('cdk_test002', gate, approver='cli', log_dir=Path(tmp))
    record = json.loads(Path(path).read_text())
    assert record['approver'] == 'cli'
    assert 'approver_arn' in record      # may be null without real AWS creds
    assert 'approver_account' in record
    print('PASS: approval record fields OK')
    print('  approver_arn:', record['approver_arn'])
"
```

---

## Step 4 — Verify regen prompt contains findings

```bash
python -c "
from AIgen.run_cdk_regen import build_cdk_regen_prompt

gate = {
    'decision': 'reject', 'score': 90,
    'findings': [
        {'severity': 'critical', 'source': 'checkov', 'message': 'SSH port 22 open to 0.0.0.0/0',
         'resource_id': 'MySecurityGroup', 'template': 'MyStack.json'},
        {'severity': 'high', 'source': 'iac_security_gate', 'message': 'S3 bucket not encrypted',
         'resource_id': 'MyBucket', 'template': 'MyStack.json'},
    ]
}
prompt = build_cdk_regen_prompt('Create an S3 bucket and EC2 instance', gate, attempt=1)
assert 'SSH port 22' in prompt
assert 'S3 bucket not encrypted' in prompt
assert 'attempt 1' in prompt
assert 'reject' in prompt
print('PASS: regen prompt contains all findings')
"
```

---

## Step 5 — CLI reject path: rejection record written, exit code 22

Run the existing CDK project (which likely has some findings) without `--deploy`:

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --no-checkov --no-cfn-lint --no-infracost --no-aws-config \
  2>&1 | python -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        if obj.get('stage') in ('gate', 'decision', 'rejection_record'):
            print(obj)
    except Exception:
        pass
"
echo "Exit code: $status"
```

**Expected**: if gate decision is `reject`, you see a `rejection_record` stage line with a path like `logs/rejections/rejection_cdk_*.json` and exit code 22. Verify the file exists:

```bash
ls -lh logs/rejections/
cat logs/rejections/rejection_cdk_*.json | python -m json.tool | head -30
```

---

## Step 6 — CLI review + manual-approve path: approval record written

This requires a stack that scores in the 21–60 band. The quickest way is to override the run with `--aws-config-violations 5` (5 × 5 = 25 pts → review band):

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --no-checkov --no-cfn-lint --no-infracost --no-aws-config \
  --aws-config-violations 5 \
  --manual-approve \
  2>&1 | grep -E '"stage"'

ls -lh logs/approvals/
cat logs/approvals/approval_cdk_*.json | python -m json.tool | head -20
```

**Expected**: `approval_record` stage printed, file written with `approver: "cli"`, `approver_arn` field present (null if no AWS creds configured).

---

## Step 7 — CLI SNS notification (dry-run via mock)

```bash
python -c "
import os, json
os.environ['SNS_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:000000000000:test-topic'
from unittest.mock import patch, MagicMock
from pipeline.notifier import get_notifier

notifier = get_notifier()
mock_client = MagicMock()
with patch('boto3.client', return_value=mock_client):
    notifier.send('reject', {
        'run_id': 'cdk_test999', 'decision': 'reject', 'score': 90,
        'findings': [{'severity': 'critical', 'source': 'checkov',
                      'message': 'SSH open', 'resource_id': 'SG', 'template': 'T.json'}]
    })
    call_args = mock_client.publish.call_args
    assert call_args is not None, 'FAIL: publish not called'
    kwargs = call_args.kwargs
    assert kwargs['Subject'] == 'CDK Pipeline: reject'
    payload = json.loads(kwargs['Message'])
    assert payload['event_type'] == 'reject'
    assert payload['run_id'] == 'cdk_test999'
    assert len(payload['top_findings']) == 1
    print('PASS: SNS publish called with correct payload')
    print('  Subject:', kwargs['Subject'])
    print('  Payload keys:', list(payload.keys()))
"
```

---

## Step 8 — CLI regen loop (dry-run without real AWS, synth only)

This test invokes the regen loop but stops at the generation step (will fail on Bedrock call without credentials, which is expected — the point is to verify the loop wiring):

```bash
python AIgen/run_cdk_regen.py \
  --prompt "Create an S3 bucket with versioning enabled" \
  --project-dir GeneratedCDK \
  --max-attempts 1 \
  --provider bedrock \
  2>&1 | head -20
```

**Expected**: Either a Bedrock error (no creds) or a gate result. If you have Bedrock credentials, the loop runs fully and writes artifacts:

```bash
ls -lh logs/cdk_regen/
```

To test the `--regen-on-reject` CLI flag end-to-end (requires Bedrock creds):

```bash
python scripts/run_cdk_pipeline.py \
  --project-dir GeneratedCDK \
  --prompt "Create a secure S3 bucket with encryption and versioning" \
  --regen-on-reject \
  --max-regen-attempts 2 \
  --no-cfn-lint --no-infracost --no-aws-config \
  2>&1 | python -m json.tool
```

---

## Step 9 — UI smoke test

```bash
streamlit run ui_app.py
```

Navigate to the **CDK** tab and:

1. Prepare + Synth a project
2. After gate runs, check:
   - If decision is **reject**: `Rejection record:` path appears below the gate metrics
   - If decision is **review**: the "Manual review approved" checkbox appears
3. Tick the review checkbox — verify `Approval record:` path appears immediately beneath it
4. Check approvals for the written file:
   ```bash
   cat logs/approvals/approval_cdk_*.json | python -m json.tool
   ```

---

## Step 10 — Full audit trail check

After running both a reject and an approve scenario:

```bash
ls -lh logs/gate_reports/ logs/approvals/ logs/rejections/
```

Open one of each and verify the JSON structure is complete and consistent (`run_id` matches across gate report, approval/rejection record).