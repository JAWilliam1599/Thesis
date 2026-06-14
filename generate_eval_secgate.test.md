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