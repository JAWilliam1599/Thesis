# Hybrid Demo — End-to-End Setup (VM + Tailscale + Full Pipeline)

This walkthrough takes you from nothing to a **full hybrid run**: an AWS CDK
stack gated and deployed to the cloud, and an Ansible playbook gated and deployed
to an **on-prem VM** reached privately over **Tailscale** — using the same risk
engine for both sides, with **no code-generation step**.

```
   ┌─────────────┐   gate + deploy (cdk)     ┌──────────────┐
   │  Control    │ ─────────────────────────▶│   AWS Cloud  │
   │  machine    │                           └──────────────┘
   │ (this repo) │   gate + deploy (ansible)  ┌──────────────┐
   │             │ ──────── Tailscale ───────▶│  On-prem VM  │
   └─────────────┘        (100.x.y.z)         └──────────────┘
```

- **Control machine** = where this repo and the `.venv` live (your laptop).
- **On-prem VM** = a local Ubuntu VM (VirtualBox/UTM/multipass/Raspberry Pi).
- **Tailscale** = private mesh so the control machine reaches the VM by a stable
  `100.x` IP with no port-forwarding and no public exposure.

> Time budget: ~30–45 min the first time. AWS steps are optional — you can run
> the **entire on-prem half** with zero AWS credentials.

---

## Part 0 — Prerequisites (control machine)

```bash
cd /home/astia/Documents/Thesis/Thesis

# Python env + all tooling (ansible-core, ansible-lint, checkov, cfn-lint, boto3)
python -m venv .venv                    # skip if .venv already exists
.venv/bin/python -m pip install -r requirements.txt

# Sanity check the tools the gate needs
.venv/bin/ansible-playbook --version
.venv/bin/ansible-lint --version
.venv/bin/checkov --version
```

For the **CDK half** you additionally need the Node-based CDK CLI and AWS creds:

```bash
node --version            # Node 18+ recommended
npm install -g aws-cdk    # provides the `cdk` command
aws sts get-caller-identity   # confirms AWS credentials resolve
```

If you only want the on-prem demo, skip the CDK/AWS lines above.

---

## Part 1 — Create the on-prem VM

Any Linux VM works. Pick whichever you have:

### Option A — multipass (fastest, recommended)
```bash
# On the control machine (install multipass first: https://multipass.run)
multipass launch 22.04 --name onprem-node --cpus 2 --memory 2G --disk 10G
multipass shell onprem-node          # drops you into the VM
```

### Option B — VirtualBox / UTM / Raspberry Pi
1. Install **Ubuntu Server 22.04** (minimal is fine).
2. During install, create user `ubuntu` and **enable OpenSSH server**.
3. Boot it and log in.

Whatever you choose, you need:
- A user named **`ubuntu`** with **passwordless sudo** (matches the demo inventory).
- SSH access from the control machine.

Set up passwordless sudo on the VM (run **inside the VM**):
```bash
echo "ubuntu ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/ubuntu
sudo apt-get update
```

---

## Part 2 — Connect the VM with Tailscale (the best way)

The goal: control machine and VM join the same private tailnet; you target the
VM by a stable `100.x` IP (or MagicDNS name) instead of a fragile LAN/public IP.

### Step 2.1 — Create the tailnet & install on the control machine
1. Sign up once at https://tailscale.com (GitHub/Google login creates your tailnet).
2. On the **control machine**:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

### Step 2.2 — Register the VM with a tagged, non-interactive auth key (best practice)
Using an **auth key with a tag** (instead of personal login) makes the VM
reproducible and lets you lock down access with ACLs.

1. Admin console → **Settings → Keys → Generate auth key**
   - Reusable: off · Ephemeral: off · **Tags: `tag:onprem`**
   - (First time only) Admin console → **Access Controls**, add the tag owner:
     ```jsonc
     {
       "tagOwners": { "tag:onprem": ["your-email@example.com"] }
     }
     ```
2. **Inside the VM**, install and bring it up with that key:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --authkey tskey-auth-xxxxxxxx --advertise-tags=tag:onprem --ssh
   ```
   `--ssh` lets you SSH over the mesh; `--advertise-tags` applies the ACL tag.

### Step 2.3 — Get the VM's mesh address
**Inside the VM:**
```bash
tailscale ip -4        # prints something like 100.101.102.103  → use this
```

### Step 2.4 — (Recommended) Enable MagicDNS + lock down with an ACL
- Admin console → **DNS → enable MagicDNS**. Now the VM is reachable by name
  `onprem-node` instead of its IP.
- Admin console → **Access Controls**, restrict who can reach the node:
  ```jsonc
  {
    "tagOwners": { "tag:onprem": ["your-email@example.com"] },
    "acls": [
      { "action": "accept", "src": ["your-laptop-name"], "dst": ["tag:onprem:22"] }
    ]
  }
  ```

### Step 2.5 — Verify connectivity from the control machine
```bash
tailscale status                       # VM should appear as onprem-node
ssh ubuntu@100.101.102.103             # or: ssh ubuntu@onprem-node  (MagicDNS)
```
If SSH works, Ansible will too.

---

## Part 3 — Point the demo at your VM

Edit [inventory.ini](inventory.ini) and replace the placeholder address with the
Tailscale IP from Step 2.3 (or the MagicDNS name `onprem-node`):

```ini
[webnodes]
onprem-node ansible_host=100.101.102.103 ansible_user=ubuntu
```

Confirm Ansible can reach it (run on the **control machine**, from the repo root):
```bash
.venv/bin/ansible -i examples/hybrid-demo/ansible/inventory.ini webnodes -m ping
# expected: onprem-node | SUCCESS => {"ping": "pong"}
```

> Prefer no inventory file? Skip the edit and pass `--target-host 100.101.102.103`
> on the pipeline command instead — it builds an inline inventory for you.

---

## Part 4 — Gate-only dry run (no deploy, totally safe)

Always start here. Nothing is deployed; both sides are just scored.

```bash
cd /home/astia/Documents/Thesis/Thesis

.venv/bin/python scripts/run_hybrid_pipeline.py \
    --cdk-path examples/hybrid-demo/cdk \
    --ansible-path examples/hybrid-demo/ansible
```

What happens:
- **CDK branch:** `cdk synth` → security gate (checkov, cfn-lint, infracost, AWS
  Config) → risk score → diff.
- **Ansible branch:** `ansible-playbook --syntax-check` → security gate
  (ansible-lint, checkov `--framework ansible`, secret scan) → risk score.

The demo code is clean, so both should report **`pass`** (score 0). The combined
report is written to `logs/hybrid_<run_id>.json`.

On-prem only (no AWS needed):
```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
    --ansible-path examples/hybrid-demo/ansible
```

---

## Part 5 — Full pipeline WITH deploy

Deploy only happens when the gate allows it (`pass`, or `review` with
`--manual-approve`). Before deploying, the Ansible branch automatically runs
`--syntax-check` then `--check --diff` (dry run) against your VM.

### On-prem only (installs nginx on the VM over Tailscale)
```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
    --ansible-path examples/hybrid-demo/ansible \
    --deploy
```
(Using the inventory file from Part 3. To bypass it, add `--target-host 100.101.102.103`.)

Verify on the VM:
```bash
ssh ubuntu@onprem-node 'systemctl is-active nginx'   # → active
```

### Both halves (cloud + on-prem) in one run
```bash
.venv/bin/python scripts/run_hybrid_pipeline.py \
    --cdk-path examples/hybrid-demo/cdk \
    --ansible-path examples/hybrid-demo/ansible \
    --deploy
```

If a branch lands in the **review** band (score 21–80), add `--manual-approve`
to allow the deploy; otherwise it is held.

---

## Part 6 — (Optional) Make the VM visible to AWS monitoring

Register the VM as an SSM **managed instance** so it shows up next to your EC2
instances for compliance/patch visibility.

1. On the **control machine** (needs AWS creds), create an activation:
   ```bash
   .venv/bin/python Monitor/ssm_hybrid.py --create --name onprem-node
   ```
   This prints an install+register snippet (SSM agent download + `-register`).
2. Copy that snippet and run it **inside the VM** (it's reachable over Tailscale).
3. Build the AWS↔on-prem dashboard:
   ```bash
   .venv/bin/python Monitor/hybrid_dashboard.py --create --targets onprem-node
   ```

---

## Part 7 — Status & observability

```bash
# Last gate score/decision per target (from SSM)
.venv/bin/python scripts/run_hybrid_pipeline.py --query-status

# On-prem mesh status: SSM nodes + compliance + Tailscale devices
.venv/bin/python scripts/run_hybrid_pipeline.py --hybrid-status
```

To populate the Tailscale section of `--hybrid-status`, add a read-only API token
(admin console → **Settings → Keys → API access token**) to a `.env` at the repo root:
```bash
echo 'TAILSCALE_API_KEY=tskey-api-xxxxxxxx' >> .env
echo 'TAILSCALE_TAILNET=your-tailnet-name'  >> .env   # or "-" for default
```

---

## Useful flags

| Flag | Effect |
|---|---|
| `--base-ref HEAD~1` | Scan only git-changed YAML (changed-file scoping) |
| `--target-host <ip>` | Inline inventory instead of `inventory.ini` |
| `--playbook <file>` / `--inventory <file>` | Override auto-detection |
| `--manual-approve` | Allow deploy for `review`-band (21–80) results |
| `--deploy` | Actually deploy each gate-approved branch |
| `--bootstrap` | Run `cdk bootstrap` before the CDK synth |
| `--no-checkov` / `--no-ansible-lint` / `--no-secret-scan` | Skip a scanner |
| `--no-infracost` / `--no-cfn-lint` / `--no-aws-config` | Skip a CDK-side scanner |
| `--verbose` | Debug logging |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ansible ... -m ping` fails | Re-check `tailscale status`; confirm `ssh ubuntu@<ip>` works and the user is `ubuntu` |
| Ansible deploy fails on sudo | Ensure passwordless sudo on the VM (Part 1) |
| Gate says `not_installed` for a scanner | Re-run `pip install -r requirements.txt`; use `.venv/bin/python` |
| `cdk: command not found` | `npm install -g aws-cdk`, or skip the CDK half |
| CDK branch fails on credentials | `aws sts get-caller-identity`; or run on-prem only |
| `--check` reports "unreachable" but gate passed | Dry-run needs the VM up; it's advisory when you're not deploying |

---

## Recommended first-time order

1. Part 0 — install tooling.
2. Part 4 — gate-only run, confirm **both `pass`**.
3. Parts 1–3 — VM + Tailscale + `ansible ... -m ping` succeeds.
4. Part 5 (on-prem `--deploy`) — confirm nginx is `active` on the VM.
5. Parts 6–7 — optional AWS monitoring + status dashboards.
