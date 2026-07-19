# Hybrid Web-App Demo — "502 → Diagnose → Fix → Re-deploy through the Gated Pipeline"

A presenter's runbook for the hybrid guestbook demo. The story: we deploy a
website whose **database lives on-prem**, hit a real **HTTP 502**, diagnose it
across the AWS ↔ on-prem boundary, fix the *code*, and let the **existing
hybrid pipeline** (security gate → manual approval → deploy) ship the fix — with
**no AI code generation** and **without disturbing the already-deployed
resources**.

> Runnable companion: [`demo.sh`](demo.sh). Backup code lives in
> [`demo-materials/before/`](demo-materials/before) (buggy) and
> [`demo-materials/after/`](demo-materials/after) (fixed).

---

## 0. Architecture (what the audience is looking at)

```
Browser
  │  HTTPS
  ▼
CloudFront ──► S3 (static frontend, private via OAC)
  │
  │  /prod/guestbook  (fetch)
  ▼
API Gateway ──► Lambda (in VPC private-isolated subnets)
                  │  reads DB creds from Secrets Manager (VPC endpoint, no NAT)
                  │  psycopg2 ──► TCP 5432
                  ▼
        Tailscale subnet-router EC2 (in VPC)
                  │  Tailscale mesh (WireGuard)
                  ▼
        On-prem PostgreSQL  (multipass VM `onprem-db`, Ansible-provisioned)
```

The AWS half is CDK (`examples/hybrid-webapp-demo/cdk`); the on-prem half is
Ansible (`examples/hybrid-webapp-demo/ansible`). Both halves are gated
**independently** by the same risk-scoring engine.

**Live reference values** (this environment — account `926208928139`, `us-east-1`):

| Thing | Value |
|-------|-------|
| Site (CloudFront) | `https://d3btj2zer1bf7b.cloudfront.net` |
| API endpoint | `https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook` |
| Stack | `HybridWebappStack` |
| On-prem DB (Tailscale IP) | `100.112.100.124` (`onprem-db`) |
| Tailscale router EC2 | `i-0da459c57f46c296a` (ENI `eni-05dbe66ca8ccb150a`) |
| Router SG / Lambda SG | `sg-0e2e05c6c9b118e0e` / `sg-0be3c1f3f25c7badb` |
| Isolated route tables | `rtb-097e8b756a09ac586`, `rtb-0bda2272d9b82eb33` |

---

## 1. Prerequisites (before the audience arrives)

- AWS credentials active: `aws sts get-caller-identity` returns your account.
- Tailscale API creds in the environment (loaded from `.env`):
  `TAILSCALE_API_KEY`, `TAILSCALE_TAILNET` (`taile9a415.ts.net`).
- The on-prem VM is up and on the tailnet: `multipass list` shows `onprem-db`
  Running; `tailscale status` lists it.
- The stack has been created **once** already (so `SiteUrl`/`ApiUrl` exist).
- Python venv at `.venv` with the pipeline deps installed.

> **fish-shell note.** All Python/pipeline commands are shell-agnostic. For the
> few shell-local commands, fish differs from bash:
> `set -gx VAR value` (not `export VAR=value`) and `(cmd)` (not `$(cmd)`).
> `demo.sh` is a **bash** script — run it with `bash demo.sh <cmd>`.

---

## 2. Act I — "It deployed… but the site is broken" (the 502)

**Say:** *"The infrastructure deployed green. Let's open the site."*

Open `https://d3btj2zer1bf7b.cloudfront.net/` → the page loads, but the
guestbook shows **"Could not load entries: HTTP 502"**.

**Show the raw API:**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook
# HTTP 502
```

**Say:** *"The frontend and API are fine — the Lambda can't reach the on-prem
database. This is the classic hybrid failure: the code is 'correct', but the
network path across the cloud/on-prem boundary isn't."*

> To reproduce this from scratch: `bash demo.sh break` installs the buggy code
> ([`demo-materials/before/`](demo-materials/before)) and re-deploys.

---

## 4. Act III — The fix 

Two files change. Diff them live against the backups:

```bash
diff -u demo-materials/before/app.py   ../cdk/app.py
diff -u demo-materials/before/site.yml ../ansible/site.yml
```

**CDK — [`cdk/app.py`](../cdk/app.py):**
1. Router SG now **accepts 5432 from the Lambda SG** (Layer 3):
   ```python
   tailscale_sg.add_ingress_rule(
       lambda_sg, ec2.Port.tcp(5432),
       "Forwarded PostgreSQL from backend Lambda to on-prem DB",
   )
   ```
2. VPC now **routes the Tailscale CGNAT range** to the router (Layer 2):
   ```python
   routed_cidrs = {"OnPrem": onprem_db_cidr, "Tailnet": "100.64.0.0/10"}
   ```

**CDK context — [`cdk/cdk.json`](../cdk/cdk.json):** the DB host / CIDR are now
**pinned in context** so the pipeline's plain `cdk deploy --all` synthesises the
correct values (the pipeline passes no `-c` flags):
```json
"context": { "onprem_db_host": "100.112.100.124", "onprem_db_cidr": "192.168.64.0/24", ... }
```

**Ansible — [`ansible/site.yml`](../ansible/site.yml):** a new task grants the
app role access after the schema is applied (Layer 5):
```yaml
- name: Grant the application role access to the schema objects
  ansible.builtin.command:
    argv: [psql, "-d", "{{ db_name }}", "-c", "GRANT ALL ON ALL TABLES ... TO {{ db_user }} ..."]
  become: true
  become_user: postgres
```

**Layer 4** (Tailscale route approval) is a tailnet-level runtime action, not a
CloudFormation resource — it stays a one-time approval step (`demo.sh
approve-route` or the admin console).

---

## 5. Act IV — Ship the fix through the gated pipeline (no codegen)

**Say:** *"We didn't regenerate anything with AI — we edited existing IaC. The
hybrid pipeline is 'bring your own code': it gates each half and deploys what
the gate allows."*

**Step 1 — Sync the DB password for the Ansible branch (never printed):**

> Only required on first provision

```bash
# bash:
export ONPREM_DB_PASSWORD="$(aws secretsmanager get-secret-value \
  --secret-id "$(aws cloudformation describe-stacks --stack-name HybridWebappStack \
     --query "Stacks[0].Outputs[?OutputKey=='DbSecretArn'].OutputValue" --output text)" \
  --query SecretString --output text \
  | python -c 'import sys,json;print(json.load(sys.stdin)["password"])')"
# fish:  set -gx ONPREM_DB_PASSWORD (…same pipeline…)
```

**Step 2 — Gate-only first (safe dry run):**

```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
  --cdk-path examples/hybrid-webapp-demo/cdk \
  --ansible-path examples/hybrid-webapp-demo/ansible --verbose
```

Expected gate result (talking point — the stack deliberately leaves WAF /
CloudFront access-logging gaps so the engine has real findings):

| Branch | Score | Decision |
|--------|-------|----------|
| CDK | **70** | **review** (needs manual approval) |
| Ansible | **0** | **pass** |

**Step 3 — Deploy with approval:**

```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
  --cdk-path examples/hybrid-webapp-demo/cdk \
  --ansible-path examples/hybrid-webapp-demo/ansible \
  --deploy --manual-approve --verbose
```

What happens:
- **CDK decision:** `Manual review approved.` → `cdk deploy --all
  --require-approval never`.
- CloudFormation computes a **changeset** — it only *adds* the SG ingress rule
  and the Tailnet routes. Result: `UPDATE_COMPLETE`.
- **Ansible:** `Risk gate passed.` → playbook runs (`ok=13 changed=1 failed=0`),
  applying the GRANT.
- An approval record is written to `logs/approvals/`, the gate report to
  `logs/gate_reports/`, and a combined run summary to
  `logs/hybrid_<timestamp>.json`.

> One-liner equivalent: `bash demo.sh fix` (installs `after/`, syncs the
> password, runs the gated deploy, approves the route, curls the API).

---

## 6. Act V — Verify (the payoff)

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook
# HTTP 200
curl -s https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook | python -m json.tool
```

Reload `https://d3btj2zer1bf7b.cloudfront.net/` → the guestbook lists the
seed rows (Ada, Grace), and submitting the form inserts a new row into the
**on-prem** PostgreSQL over the Tailscale mesh.

**Say:** *"200. The website is live, the data is genuinely on-prem, and the fix
shipped through the same gated pipeline any change would — reviewed, approved,
logged."*

---

## 7. Q&A talking points (the two questions this demo answers)

**"Does the pipeline run start-to-end without code generation?"**
Yes. AI generation lives in a *separate* tool (`generation/`). The hybrid pipeline is
explicitly "bring your own code": `synth → security gate → diff → deploy` for
CDK, and `syntax-check → gate → check → deploy` for Ansible. You point it at
already-written code with `--cdk-path` / `--ansible-path`.

**"Does the deploy step damage previously deployed resources?"**
No. `cdk deploy` is a CloudFormation **changeset** — it only modifies drift.
In this run the only changes were *additive* (one SG ingress rule + two routes),
the stack went straight to `UPDATE_COMPLETE`, and the existing VPC, CloudFront,
Lambda, and the generated **DB secret value were preserved** (Secrets Manager
does not regenerate on update). The seed rows survived and a new row inserted
cleanly. Ansible is idempotent (schema `IF NOT EXISTS`, seed guarded by
`WHERE NOT EXISTS`, role creation guarded by a `pg_roles` check, GRANT is
naturally idempotent).

---

## 8. Reset / re-run cheatsheet

| Goal | Command |
|------|---------|
| Check the site right now | `bash demo.sh status` |
| Reproduce the 502 (buggy code) | `bash demo.sh break` |
| Ship the fix (gated deploy) | `bash demo.sh fix` |
| Gate only, no deploy | `bash demo.sh gate` |
| Approve the Tailscale route | `bash demo.sh approve-route` |

**Caveat — hand-made drift vs. CloudFormation.** If you previously added the
`100.64.0.0/10` route or the router SG ingress **by hand** (AWS CLI), delete
them before a code-driven deploy, or CloudFormation errors with
`RouteAlreadyExists` / `InvalidPermission.Duplicate`:

```bash
aws ec2 delete-route --route-table-id rtb-097e8b756a09ac586 --destination-cidr-block 100.64.0.0/10
aws ec2 delete-route --route-table-id rtb-0bda2272d9b82eb33 --destination-cidr-block 100.64.0.0/10
aws ec2 revoke-security-group-ingress --group-id sg-0e2e05c6c9b118e0e \
  --protocol tcp --port 5432 --source-group sg-0be3c1f3f25c7badb
```
