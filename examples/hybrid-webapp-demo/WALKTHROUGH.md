# Hybrid Web-App Demo — Website on AWS, Database On-Prem

A realistic hybrid application: a **guestbook website** whose frontend and API
run entirely on **AWS serverless**, while its **PostgreSQL database lives
on-prem** and is reached privately over **Tailscale**. Both halves are gated by
the same security/risk engine before anything is deployed.

```
        Browser
          │  HTTPS
          ▼
   ┌──────────────┐        ┌──────────────────────────────────────────┐
   │  CloudFront  │──OAC──▶ │  S3 (private static frontend)            │
   └──────┬───────┘        └──────────────────────────────────────────┘
          │  /prod/guestbook (fetch)
          ▼
   ┌──────────────┐   ┌───────────────────────────┐
   │ API Gateway  │──▶│ Lambda (in VPC, psycopg2) │
   └──────────────┘   └────────────┬──────────────┘
                                   │  reads creds from Secrets Manager (VPC endpoint)
                                   │  TCP 5432
                                   ▼
                    ┌───────────────────────────────┐
                    │ Tailscale subnet-router EC2    │  (in the VPC)
                    └───────────────┬───────────────┘
                                    │  Tailscale mesh (100.x)
                                    ▼
                    ┌───────────────────────────────┐
                    │  On-prem PostgreSQL server     │  (Ansible-provisioned)
                    │  also a Tailscale subnet router│
                    └───────────────────────────────┘
```

- **AWS side (CDK):** S3 + CloudFront (frontend), API Gateway + Lambda (backend),
  Secrets Manager (DB creds), a VPC with a Secrets Manager interface endpoint,
  and a **Tailscale subnet-router EC2** so the in-VPC Lambda can route to the
  on-prem subnet.
- **On-prem side (Ansible):** installs and configures **PostgreSQL**, loads the
  guestbook schema/seed data, and runs **Tailscale as a subnet router** that
  advertises the DB subnet back to your tailnet.

> This demo is intentionally *mostly* hardened. A couple of best-practice gaps
> (no WAF and no access logging on CloudFront) are left in on purpose so the
> risk-scoring engine has real findings to report. Expect a `review` rather than
> a perfectly clean `pass` on the CDK branch — that is the point.

---

## Part 0 — Prerequisites (control machine)

```bash
cd /home/astia/Documents/Thesis/Thesis

# Python env + gate tooling (checkov, cfn-lint, ansible-core, ansible-lint, boto3)
python -m venv .venv                    # skip if .venv already exists
.venv/bin/python -m pip install -r requirements.txt

# CDK needs aws-cdk-lib in the venv (not pinned in requirements.txt) …
.venv/bin/python -m pip install aws-cdk-lib constructs

# … and the Node-based CDK CLI for `cdk synth` / `cdk deploy`
npm install -g aws-cdk
cdk --version
```

For the AWS deploy you also need working credentials:

```bash
aws sts get-caller-identity     # confirms AWS credentials resolve
```

You can run the **entire on-prem half with zero AWS credentials** — only the CDK
branch touches AWS.

---

## Part 1 — Create the on-prem database VM

Any Linux host works (multipass / VirtualBox / UTM / Raspberry Pi). It will run
both PostgreSQL and the Tailscale subnet router.

```bash
# Fastest: multipass
multipass launch 22.04 --name onprem-db --cpus 2 --memory 2G --disk 10G
multipass shell onprem-db
```

Inside the VM, ensure:

- a user named **`ubuntu`** with **passwordless sudo**:
  ```bash
  echo "ubuntu ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ubuntu
  sudo apt-get update
  ```
- **OpenSSH server** installed and reachable from the control machine.

**Give the control machine key-based SSH access** (Ansible connects over SSH,
not `multipass shell`). If you have no key yet, generate one, then inject its
public half into the VM:

```bash
# On the control machine — create a key if you don't already have one
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# Authorize it on the VM (multipass runs the command as the ubuntu user)
multipass exec onprem-db -- bash -c \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
   echo '$(cat ~/.ssh/id_ed25519.pub)' >> ~/.ssh/authorized_keys && \
   chmod 600 ~/.ssh/authorized_keys"
```

> Not using multipass? Use `ssh-copy-id ubuntu@<vm-ip>` (needs password auth
> enabled once) or paste the public key into `~/.ssh/authorized_keys` on the VM.

Note the VM's LAN subnet (e.g. `192.168.64.0/24`) — you will advertise it from
Tailscale and pass it to the CDK stack as `onprem_db_cidr`.

---

## Part 2 — Join both ends to Tailscale

1. Create a Tailscale account and an **auth key** (Admin console → Settings →
   Keys). Tag it (e.g. `tag:onprem`) if you use ACL tags.

2. **On the on-prem VM**, install Tailscale and bring it up as a **subnet
   router** advertising the DB subnet, so AWS can route to it:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up \
       --advertise-routes=192.168.64.0/24 \
       --accept-routes \
       --authkey tskey-XXXXXXXX
   ```

3. In the Tailscale admin console, **approve the advertised route** for the VM.

4. Note the VM's Tailscale IP (`100.x.y.z`) — this is `onprem_db_host`.

The AWS-side Tailscale router (an EC2 instance) is created for you by the CDK
stack; you approve its route after deploy (Part 6).

---

## Part 3 — Point the demo at your database host

Edit [ansible/inventory.ini](ansible/inventory.ini):

```ini
[dbservers]
onprem-db ansible_host=100.112.100.124 ansible_user=ubuntu
```

Confirm reachability from the control machine (repo root):

```bash
ANSIBLE_HOST_KEY_CHECKING=False \
  .venv/bin/ansible -i examples/hybrid-webapp-demo/ansible/inventory.ini \
    dbservers -m ping
# expected: onprem-db | SUCCESS => {"ping": "pong"}
```

> Host-key checking is disabled for this ephemeral VM via
> [ansible/ansible.cfg](ansible/ansible.cfg); the pipeline runs from that
> directory so it applies automatically. Only the one-off command above (run
> from the repo root) needs the `ANSIBLE_HOST_KEY_CHECKING=False` prefix. If you
> still see `Permission denied (publickey)`, redo the SSH key step in Part 1.

Review the tunables in
[ansible/group_vars/dbservers.yml](ansible/group_vars/dbservers.yml) — database
name, user, allowed CIDRs. **Do not** put the password here; it is read from the
`ONPREM_DB_PASSWORD` environment variable at deploy time (Part 5/7).

---

## Part 4 — Gate-only dry run (no deploy, totally safe)

Always start here. Nothing is deployed; both branches are just scored.

```bash
cd /home/astia/Documents/Thesis/Thesis

.venv/bin/python scripts/run_hybrid_pipeline.py \
    --cdk-path examples/hybrid-webapp-demo/cdk \
    --ansible-path examples/hybrid-webapp-demo/ansible
```

What happens:

- **CDK branch:** `cdk synth` → security gate (checkov, cfn-lint, infracost, AWS
  Config) → risk score. Expect a **`review`** decision driven by the intentional
  CloudFront WAF / access-logging findings.
- **Ansible branch:** `ansible-playbook --syntax-check` → security gate
  (ansible-lint, checkov `--framework ansible`, secret scan) → risk score. The
  playbook is lint-clean and holds no hardcoded secrets, so expect **`pass`**.

The combined report is written to `logs/hybrid_<run_id>.json`.

On-prem only (no AWS needed):

```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
    --ansible-path examples/hybrid-webapp-demo/ansible
```

---

## Part 5 — Deploy the on-prem database

Deploy happens only when the gate allows it. The Ansible branch first runs
`--syntax-check`, then `--check --diff` (dry run) against your VM.

```bash
# Password that Ansible will set on the DB role. Keep it out of shell history.
read -rs ONPREM_DB_PASSWORD; export ONPREM_DB_PASSWORD   # bash/zsh
# fish shell equivalent:  read -sgx ONPREM_DB_PASSWORD

.venv/bin/python scripts/run_hybrid_pipeline.py \
    --ansible-path examples/hybrid-webapp-demo/ansible \
    --deploy
```

This installs PostgreSQL, creates the `guestbook` database and `appuser` role,
loads the schema/seed rows, opens `pg_hba.conf`/`ufw` to the AWS + Tailscale
CIDRs, and (via Tailscale from Part 2) makes the DB reachable from AWS.

---

## Part 6 — Deploy the AWS website

The Secrets Manager secret must hold the **same** password you set on-prem.
Pass the on-prem details as CDK context so they match your environment:

```bash
cd examples/hybrid-webapp-demo/cdk

# One-time: populate the Docker-free psycopg2 layer
pip install \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --target layers/psycopg2/python psycopg2-binary

# Bootstrap once per account/region, then deploy
cdk bootstrap
cdk deploy \
  -c onprem_db_cidr=192.168.64.0/24 \
  -c onprem_db_host=100.64.0.10 \
  -c db_name=guestbook \
  -c db_user=appuser
```

After deploy:

1. Note the outputs: `SiteUrl`, `ApiUrl`, `DbSecretArn`, `VpcCidr`,
   `TailscaleRouterInstanceId`.
2. **SSH to the Tailscale router EC2** (via SSM Session Manager) and bring it up
   so the VPC ↔ on-prem route works, then approve its route in the admin console:
   ```bash
   sudo tailscale up --advertise-routes=<VpcCidr> --accept-routes --authkey tskey-XXXX
   ```
3. Set the Secrets Manager password to match on-prem:
   ```bash
   aws secretsmanager put-secret-value --secret-id <DbSecretArn> \
     --secret-string "$(aws secretsmanager get-secret-value --secret-id <DbSecretArn> \
        --query SecretString --output text \
        | ONPREM_DB_PASSWORD="$ONPREM_DB_PASSWORD" \
          python -c 'import os,sys,json;d=json.load(sys.stdin);d["password"]=os.environ["ONPREM_DB_PASSWORD"];print(json.dumps(d))')"
   ```
4. Point the frontend at the API and upload it to the bucket:
   ```bash
   # Put the ApiUrl output into config.js
   printf 'window.APP_CONFIG = { apiBaseUrl: "%s" };\n' "<ApiUrl>" \
     > ../frontend/config.js

   # Upload the static site and refresh the CDN
   aws s3 sync ../frontend "s3://<FrontendBucketName>"
   aws cloudfront create-invalidation \
     --distribution-id <DistributionId> --paths '/*'
   ```

Open `SiteUrl` in a browser — the guestbook should list the seed rows served
from your on-prem PostgreSQL, and new entries persist there.

### Gating both branches in one shot

You can gate-and-deploy both IaC branches with a single command:

```bash
export ONPREM_DB_PASSWORD=...    # as in Part 5
.venv/bin/python scripts/run_hybrid_pipeline.py \
    --cdk-path examples/hybrid-webapp-demo/cdk \
    --ansible-path examples/hybrid-webapp-demo/ansible \
    --deploy --manual-approve      # --manual-approve lets a `review` proceed
```

> **This is not an end-to-end "working website" button.** It runs only the two
> gated IaC deploys — `cdk deploy --all` (with the **default** context in
> `app.py`, *not* your `-c onprem_db_*` overrides) and `ansible-playbook site.yml`.
> It does **not** populate the psycopg2 layer, bootstrap the account, sync the
> DB password into Secrets Manager, bring up/approve the AWS Tailscale route, or
> upload the frontend. For a real deploy you still need the one-time layer step
> and the post-deploy steps 1–4 above. To match your environment, either edit
> the context defaults in [cdk/app.py](cdk/app.py) or run `cdk deploy` manually
> with `-c` overrides as shown above.

---

## Part 7 — Status & observability

```bash
# Last gate result per target (from SSM)
.venv/bin/python scripts/run_hybrid_pipeline.py --query-status

# SSM managed nodes + Tailscale devices (needs TAILSCALE_API_KEY)
.venv/bin/python scripts/run_hybrid_pipeline.py --hybrid-status
```

---

## Part 8 — Cleanup

```bash
# AWS
cd examples/hybrid-webapp-demo/cdk
aws s3 rm "s3://<FrontendBucketName>" --recursive   # empty the bucket first
cdk destroy

# On-prem (optional): remove PostgreSQL + Tailscale on the VM, or just delete it
multipass delete onprem-db && multipass purge
```

---

## File map

| Path | Purpose |
|------|---------|
| [cdk/app.py](cdk/app.py) | `HybridWebappStack` — VPC, Tailscale router, Lambda, API GW, CloudFront, S3, Secrets Manager |
| [cdk/lambda/handler.py](cdk/lambda/handler.py) | Backend API — psycopg2 queries to the on-prem DB |
| [cdk/layers/psycopg2/](cdk/layers/psycopg2/README.md) | Docker-free psycopg2 Lambda layer |
| [frontend/](frontend/index.html) | Static guestbook site (served via CloudFront) |
| [ansible/site.yml](ansible/site.yml) | Provisions on-prem PostgreSQL + schema/seed |
| [ansible/group_vars/dbservers.yml](ansible/group_vars/dbservers.yml) | DB name/user/CIDRs; password via env lookup |
| [ansible/files/schema.sql](ansible/files/schema.sql) | Guestbook table + seed data |
| [ansible/inventory.ini](ansible/inventory.ini) | Points at your on-prem DB host |

## Connectivity notes

- **Lambda → on-prem** works because the Lambda runs in the VPC, the VPC route
  table sends the `onprem_db_cidr` to the Tailscale router EC2, and both
  Tailscale routers advertise each other's subnets.
- **No NAT gateway** is used; the Lambda reaches Secrets Manager through an
  interface VPC endpoint.
- The **DB password is never committed** — Ansible reads it from
  `ONPREM_DB_PASSWORD`, and AWS stores it in Secrets Manager. Keep the two in
  sync (Part 6, step 3).
