# Hybrid Web-App Demo — "Add a Feature → Gate → Re-deploy through the Pipeline"

A presenter's runbook for the hybrid guestbook demo. The story: we already have
a **working** website whose **database lives on-prem**, and we want to **add a
small feature** — a per-entry **"like" counter**. That one feature changes
**both** IaC halves (AWS/CDK *and* on-prem/Ansible), and we let the **existing
hybrid pipeline** (security gate → manual approval → deploy) ship it — with **no
AI code generation** and **without disturbing the already-deployed resources**.

> Companion of [`../demo-hybrid/DEMO_SCRIPT.md`](../demo-hybrid/DEMO_SCRIPT.md),
> which tells the *fix-a-502* story. This one is the *add-a-feature* story and
> starts from that demo's fixed, working end state.
>
> Runnable companion: [`demo.sh`](demo.sh). Backup code lives in
> [`demo-materials/baseline/`](demo-materials/baseline) (pre-feature) and
> [`demo-materials/feature/`](demo-materials/feature) (with likes).

---

## 0. Architecture (what the audience is looking at)

```
Browser
  │  HTTPS
  ▼
CloudFront ──► S3 (static frontend, private via OAC)
  │
  │  /prod/guestbook            (fetch: list + add)
  │  /prod/guestbook/{id}/like  (fetch: NEW — increment likes)
  ▼
API Gateway ──► Lambda (in VPC private-isolated subnets)
                  │  reads DB creds from Secrets Manager (VPC endpoint, no NAT)
                  │  psycopg2 ──► TCP 5432
                  ▼
        Tailscale subnet-router EC2 (in VPC)
                  │  Tailscale mesh (WireGuard)
                  ▼
        On-prem PostgreSQL  (multipass VM `onprem-db`, Ansible-provisioned)
                             guestbook table now has a `likes` column
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
| Tailscale router EC2 | `i-0da459c57f46c296a` |

---

## 1. Prerequisites (before the audience arrives)

- AWS credentials active: `aws sts get-caller-identity` returns your account.
- Tailscale API creds in the environment (loaded from `.env`):
  `TAILSCALE_API_KEY`, `TAILSCALE_TAILNET` (`taile9a415.ts.net`).
- The on-prem VM is up and on the tailnet: `multipass list` shows `onprem-db`
  Running; `tailscale status` lists it.
- **The stack is already deployed and healthy** — `bash demo.sh status` returns
  **HTTP 200** and lists the seed rows (Ada, Grace). This is the fixed end state
  of the `demo-hybrid` demo.
- Python venv at `.venv` with the pipeline deps installed.

> **fish-shell note.** All Python/pipeline commands are shell-agnostic. For the
> few shell-local commands, fish differs from bash:
> `set -gx VAR value` (not `export VAR=value`) and `(cmd)` (not `$(cmd)`).
> `demo.sh` is a **bash** script — run it with `bash demo.sh <cmd>`.

---

## 2. Act I — "The site works. Now we want a new feature."

**Say:** *"The guestbook is live and green — the data is genuinely on-prem. A
product request comes in: let people **like** an entry."*

Show it working first:

```bash
bash demo.sh status
# HTTP 200  + the seed entries (Ada, Grace)
```

Open `https://d3btj2zer1bf7b.cloudfront.net/` → the guestbook lists the rows,
no like buttons yet.

**Say:** *"A 'like' button sounds trivial, but in a hybrid app it touches both
sides of the boundary: the **on-prem database** needs a place to store the
count, and the **AWS API** needs a way to increment it. So one small feature is
really two coordinated IaC changes — gated independently."*

---

## 3. Act II — The change (in code, two halves)

Diff the feature against the pre-feature baseline:

```bash
cd examples/hybrid-webapp-demo/demo-feature
diff -u demo-materials/baseline/ansible/files/schema.sql demo-materials/feature/ansible/files/schema.sql
diff -u demo-materials/baseline/ansible/site.yml         demo-materials/feature/ansible/site.yml
diff -u demo-materials/baseline/cdk/app.py               demo-materials/feature/cdk/app.py
diff -u demo-materials/baseline/cdk/lambda/handler.py    demo-materials/feature/cdk/lambda/handler.py
diff -u demo-materials/baseline/frontend/app.js          demo-materials/feature/frontend/app.js
```

**On-prem — Ansible (the data side):**
1. [`ansible/files/schema.sql`](../ansible/files/schema.sql) adds the column,
   idempotently, so existing rows keep their data:
   ```sql
   ALTER TABLE guestbook
       ADD COLUMN IF NOT EXISTS likes INTEGER NOT NULL DEFAULT 0;
   ```
2. [`ansible/site.yml`](../ansible/site.yml) gains an explicit, idempotent task
   that guarantees the column exists even on hosts provisioned before the
   feature. The existing `GRANT ALL` task already covers the new column.

**AWS — CDK (the API side):**
1. [`cdk/app.py`](../cdk/app.py) adds a new API Gateway resource + method —
   **additive**, so the existing `guestbook` GET/POST are untouched:
   ```python
   entry = guestbook.add_resource("{id}")
   like = entry.add_resource("like")
   like.add_method("POST")          # POST /guestbook/{id}/like
   ```
2. [`cdk/lambda/handler.py`](../cdk/lambda/handler.py) routes the new path to a
   `_like_entry()` that runs `UPDATE guestbook SET likes = likes + 1 …` and
   returns the new count; the list/insert queries now also return `likes`.

**Frontend:** [`frontend/app.js`](../frontend/app.js) renders a `♥ <count>`
button per entry that POSTs to `/guestbook/{id}/like` and updates in place.

**Say:** *"Nothing here was generated by AI — we edited existing IaC. The
database change is Ansible; the API change is CDK; the two ship independently
through the same gate."*

---

## 4. Act III — Gate first (safe dry run)

**Say:** *"Before anything deploys, we score both branches."*

```bash
bash demo.sh gate
```

Expected gate result (talking point — the stack deliberately leaves WAF /
CloudFront access-logging gaps so the engine has real findings; the **feature
adds no new findings** because the new API resource is a plain additive change):

| Branch | Score | Decision |
|--------|-------|----------|
| CDK | **70** | **review** (needs manual approval) |
| Ansible | **0** | **pass** |

---

## 5. Act IV — Ship the feature through the gated pipeline (no codegen)

```bash
bash demo.sh add-feature
```

Under the hood, `add-feature`:
1. installs the `feature/` code into the live project,
2. syncs `ONPREM_DB_PASSWORD` from Secrets Manager (never printed),
3. runs `run_hybrid_pipeline.py --deploy --manual-approve`:
   - **CDK:** `Manual review approved.` → `cdk deploy --all`. CloudFormation
     computes a **changeset** that only *adds* the `{id}/like` resource, method,
     and updates the Lambda code. Result: `UPDATE_COMPLETE` — VPC, CloudFront,
     the DB secret value, and existing rows are all preserved.
   - **Ansible:** `Risk gate passed.` → playbook runs, applying the idempotent
     `ALTER TABLE … ADD COLUMN IF NOT EXISTS likes …` and re-running the GRANT.
4. approves the Tailscale route (no-op if already approved),
5. uploads the updated frontend (`aws s3 sync` + CloudFront invalidation),
6. curls the API to confirm HTTP 200.

Approval/gate/run artifacts land in `logs/approvals/`, `logs/gate_reports/`,
and `logs/hybrid_<timestamp>.json`.

---

## 6. Act V — Verify (the payoff)

```bash
# The list now includes a likes field
curl -s https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook \
  | python -m json.tool

# Like entry #1 — the counter goes up and persists on-prem
curl -s -X POST \
  https://mkx5iy402a.execute-api.us-east-1.amazonaws.com/prod/guestbook/1/like \
  | python -m json.tool
# {"entry": {"id": 1, ..., "likes": 1}}
```

Reload `https://d3btj2zer1bf7b.cloudfront.net/` → each entry now has a
**♥ button**; clicking it increments the count, and the count is stored in the
**on-prem** PostgreSQL over the Tailscale mesh.

**Say:** *"One product feature, two gated IaC changes, shipped through the same
reviewed-approved-logged pipeline — and the previously deployed website, data,
and secret were never disturbed."*

---

## 7. Q&A talking points

**"Did the deploy damage anything that was already running?"**
No. `cdk deploy` is a CloudFormation **changeset** — it only *adds* the new API
resource/method and updates the Lambda code; the stack goes straight to
`UPDATE_COMPLETE`. The VPC, CloudFront, and the generated DB secret value are
preserved. Ansible is idempotent (`ADD COLUMN IF NOT EXISTS`, GRANT is naturally
idempotent), and existing rows keep their data with `likes` defaulting to 0.

**"Was any of this AI-generated?"**
No. AI generation lives in a *separate* tool (`AIgen/`). The hybrid pipeline is
"bring your own code": you point it at already-written IaC with `--cdk-path` /
`--ansible-path`, and it gates each half independently.

---

## 8. Reset / re-run cheatsheet

| Goal | Command |
|------|---------|
| Check the site right now | `bash demo.sh status` |
| Gate only, no deploy | `bash demo.sh gate` |
| Ship the likes feature (gated deploy) | `bash demo.sh add-feature` |
| Restore the pre-feature code | `bash demo.sh reset` |
| Re-upload the frontend only | `bash demo.sh deploy-frontend` |
| Approve the Tailscale route | `bash demo.sh approve-route` |

> `reset` restores the `baseline/` code but does **not** drop the `likes`
> column on-prem (the column is harmless and additive). To fully revert the
> API, run `add-feature`'s pipeline on the baseline code, or `cdk deploy` the
> baseline `app.py` manually.
