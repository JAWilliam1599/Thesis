#!/usr/bin/env bash
#
# demo.sh — runnable driver for the hybrid web-app "502 -> fix -> re-deploy"
# demo. It exercises the EXISTING hybrid pipeline (no AI code generation) on
# already-written IaC, exactly as a developer would after editing code.
#
# The paired narration lives in DEMO_SCRIPT.md (what to say at each step).
# Backup copies of the buggy and fixed code live in demo-materials/{before,after}.
#
# Usage (run from anywhere; paths are resolved relative to the repo root):
#
#   bash examples/hybrid-webapp-demo/demo-hybrid/demo.sh status       # curl the API
#   bash examples/hybrid-webapp-demo/demo-hybrid/demo.sh break        # install buggy code + deploy (reproduce 502)
#   bash examples/hybrid-webapp-demo/demo-hybrid/demo.sh fix          # install fixed code + gate + approve + deploy
#   bash examples/hybrid-webapp-demo/demo-hybrid/demo.sh approve-route # approve the Tailscale subnet route (one-time)
#   bash examples/hybrid-webapp-demo/demo-hybrid/demo.sh gate         # run the pipeline gate-only (no deploy)
#
# Prerequisites (same as the pipeline itself):
#   - AWS credentials active                 (aws sts get-caller-identity works)
#   - TAILSCALE_API_KEY / TAILSCALE_TAILNET   in the environment (loaded from .env)
#   - the on-prem multipass VM `onprem-db` up and joined to the tailnet
#   - the stack `HybridWebappStack` already created once (SiteUrl/ApiUrl exist)
#
# fish-shell users: this is a bash script — run it with `bash demo.sh <cmd>`,
# not by sourcing it. The pipeline command inside works from any shell.

set -euo pipefail

# --- Resolve repo root and key paths -------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

CDK_DIR="examples/hybrid-webapp-demo/cdk"
ANSIBLE_DIR="examples/hybrid-webapp-demo/ansible"
MATERIALS="$SCRIPT_DIR/demo-materials"
STACK="HybridWebappStack"
PY="$REPO_ROOT/.venv/bin/python"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

# --- Read a CloudFormation stack output ----------------------------------
stack_output() {
    aws cloudformation describe-stacks --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

api_url() {
    local base
    base="$(stack_output ApiUrl)"      # e.g. https://xxxx.execute-api.us-east-1.amazonaws.com/prod/
    printf '%sguestbook' "$base"
}

# --- Sync the on-prem DB password into the shell for the Ansible branch ---
# The playbook reads ONPREM_DB_PASSWORD; the role already exists so a re-run
# will NOT reset it, but we export it so a *fresh* provision stays in sync
# with the generated secret.
export_db_password() {
    local arn
    arn="$(stack_output DbSecretArn)"
    ONPREM_DB_PASSWORD="$(aws secretsmanager get-secret-value --secret-id "$arn" \
        --query SecretString --output text \
        | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["password"])')"
    export ONPREM_DB_PASSWORD
    log "ONPREM_DB_PASSWORD synced from $STACK secret (length ${#ONPREM_DB_PASSWORD})"
}

# --- curl the guestbook API and show status + body -----------------------
cmd_status() {
    local url; url="$(api_url)"
    log "GET $url"
    curl -s -o /dev/null -w "HTTP %{http_code}\n" "$url"
    curl -s "$url" | "$PY" -m json.tool 2>/dev/null || curl -s "$url"
    echo
}

# --- Run the hybrid pipeline (gate-only, no deploy) ----------------------
cmd_gate() {
    log "Hybrid pipeline — gate only (synth -> risk gate -> diff / check). No deploy."
    "$PY" scripts/run_hybrid_pipeline.py \
        --cdk-path "$CDK_DIR" \
        --ansible-path "$ANSIBLE_DIR" \
        --verbose
}

# --- Approve the Tailscale subnet route (one-time, tailnet-level) ---------
# CloudFormation re-adds the VPC route + router SG, but the router's advertised
# subnet route must be APPROVED in the tailnet before SNAT/forwarding turns on.
cmd_approve_route() {
    : "${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY (see .env)}"
    : "${TAILSCALE_TAILNET:?set TAILSCALE_TAILNET (see .env)}"
    local vpc_cidr devid
    vpc_cidr="$(stack_output VpcCidr)"
    log "Approving Tailscale subnet route $vpc_cidr on the router device"
    devid="$(curl -s -H "Authorization: Bearer $TAILSCALE_API_KEY" \
        "https://api.tailscale.com/api/v2/tailnet/$TAILSCALE_TAILNET/devices" \
        | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(next(x['id'] for x in d['devices'] if '$vpc_cidr' in x.get('advertisedRoutes',[]) or any(r=='$vpc_cidr' for r in x.get('advertisedRoutes',[]))))" 2>/dev/null || true)"
    if [ -z "${devid:-}" ]; then
        warn "Could not auto-find the router device advertising $vpc_cidr."
        warn "Approve the route manually in the Tailscale admin console."
        return 0
    fi
    curl -s -X POST -H "Authorization: Bearer $TAILSCALE_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"routes\":[\"$vpc_cidr\"]}" \
        "https://api.tailscale.com/api/v2/device/$devid/routes"
    echo
}

# --- Install a code variant (before = buggy, after = fixed) --------------
install_variant() {
    local variant="$1"   # before | after
    log "Installing '$variant' code into the live project"
    cp "$MATERIALS/$variant/app.py"   "$CDK_DIR/app.py"
    cp "$MATERIALS/$variant/site.yml" "$ANSIBLE_DIR/site.yml"
}

# --- BREAK: deploy the buggy code so the site returns 502 ----------------
cmd_break() {
    install_variant before
    export_db_password
    log "Deploying the BUGGY stack (gate will still pass CDK at review with --manual-approve)"
    "$PY" scripts/run_hybrid_pipeline.py \
        --cdk-path "$CDK_DIR" \
        --ansible-path "$ANSIBLE_DIR" \
        --deploy --manual-approve --verbose
    warn "Give the change a few seconds, then: bash demo.sh status  (expect HTTP 502)"
}

# --- FIX: deploy the corrected code through the gated pipeline ------------
cmd_fix() {
    install_variant after
    export_db_password
    log "Running the FIXED code through the pipeline (gate -> manual approve -> deploy)"
    "$PY" scripts/run_hybrid_pipeline.py \
        --cdk-path "$CDK_DIR" \
        --ansible-path "$ANSIBLE_DIR" \
        --deploy --manual-approve --verbose
    cmd_approve_route
    log "Verifying the API"
    sleep 5
    cmd_status
}

# --- Dispatch ------------------------------------------------------------
case "${1:-}" in
    status)        cmd_status ;;
    gate)          cmd_gate ;;
    break)         cmd_break ;;
    fix)           cmd_fix ;;
    approve-route) cmd_approve_route ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -n 32
        exit 1
        ;;
esac
