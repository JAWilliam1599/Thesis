#!/usr/bin/env bash
#
# demo.sh — runnable driver for the hybrid web-app "add a feature -> gate ->
# re-deploy" demo. Unlike demo-hybrid/ (which fixes a 502), this story starts
# from the already-deployed, working guestbook and ADDS a small feature — a
# per-entry "like" counter — that changes BOTH IaC halves:
#
#   * CDK:     a new  POST /guestbook/{id}/like  API resource + Lambda handler
#   * Ansible: a new  likes  column on the guestbook table (+ grant)
#
# It then ships that feature through the EXISTING hybrid pipeline (security gate
# -> manual approval -> deploy) with NO AI code generation, exactly as a
# developer would after editing existing IaC.
#
# The paired narration lives in DEMO_SCRIPT.md (what to say at each step).
# Backup copies of the pre-feature and feature code live in
# demo-materials/{baseline,feature}.
#
# Usage (run from anywhere; paths resolve relative to the repo root):
#
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh status          # curl the API
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh gate            # pipeline gate-only (no deploy)
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh add-feature     # install feature code + gate + approve + deploy + upload frontend
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh reset           # restore the pre-feature (baseline) code
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh deploy-frontend # sync frontend to S3 + invalidate CloudFront
#   bash examples/hybrid-webapp-demo/demo-feature/demo.sh approve-route   # approve the Tailscale subnet route (one-time)
#
# Prerequisites (same as the pipeline itself):
#   - AWS credentials active                 (aws sts get-caller-identity works)
#   - TAILSCALE_API_KEY / TAILSCALE_TAILNET   in the environment (loaded from .env)
#   - the on-prem multipass VM `onprem-db` up and joined to the tailnet
#   - the stack `HybridWebappStack` already deployed and WORKING (HTTP 200)
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
FRONTEND_DIR="examples/hybrid-webapp-demo/frontend"
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
# will NOT reset it, but we export it so the Ansible branch stays in sync with
# the generated secret.
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

# --- Install a code variant (baseline = pre-feature, feature = with likes) -
# Mirrors the live project layout under demo-materials/<variant>/.
install_variant() {
    local variant="$1"   # baseline | feature
    log "Installing '$variant' code into the live project"
    cp "$MATERIALS/$variant/cdk/app.py"              "$CDK_DIR/app.py"
    cp "$MATERIALS/$variant/cdk/lambda/handler.py"   "$CDK_DIR/lambda/handler.py"
    cp "$MATERIALS/$variant/ansible/site.yml"        "$ANSIBLE_DIR/site.yml"
    cp "$MATERIALS/$variant/ansible/files/schema.sql" "$ANSIBLE_DIR/files/schema.sql"
    cp "$MATERIALS/$variant/frontend/app.js"         "$FRONTEND_DIR/app.js"
    cp "$MATERIALS/$variant/frontend/styles.css"     "$FRONTEND_DIR/styles.css"
}

# --- Run the hybrid pipeline (gate-only, no deploy) ----------------------
cmd_gate() {
    log "Hybrid pipeline — gate only (synth -> risk gate -> diff / check). No deploy."
    "$PY" scripts/run_hybrid_pipeline.py \
        --cdk-path "$CDK_DIR" \
        --ansible-path "$ANSIBLE_DIR" \
        --verbose
}

# --- Upload the static frontend and refresh the CDN ----------------------
cmd_deploy_frontend() {
    local bucket dist api
    bucket="$(stack_output FrontendBucketName)"
    dist="$(stack_output DistributionId)"
    api="$(stack_output ApiUrl)"
    log "Writing config.js with ApiUrl=$api"
    printf 'window.APP_CONFIG = { apiBaseUrl: "%s" };\n' "$api" \
        > "$FRONTEND_DIR/config.js"
    log "Syncing $FRONTEND_DIR -> s3://$bucket"
    aws s3 sync "$FRONTEND_DIR" "s3://$bucket" --delete
    log "Invalidating CloudFront distribution $dist"
    aws cloudfront create-invalidation --distribution-id "$dist" --paths '/*' \
        --query 'Invalidation.Status' --output text
    echo
}

# --- Approve the Tailscale subnet route (one-time, tailnet-level) ---------
cmd_approve_route() {
    : "${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY (see .env)}"
    : "${TAILSCALE_TAILNET:?set TAILSCALE_TAILNET (see .env)}"
    local vpc_cidr devid
    vpc_cidr="$(stack_output VpcCidr)"
    log "Approving Tailscale subnet route $vpc_cidr on the router device"
    devid="$(curl -s -H "Authorization: Bearer $TAILSCALE_API_KEY" \
        "https://api.tailscale.com/api/v2/tailnet/$TAILSCALE_TAILNET/devices" \
        | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(next(x['id'] for x in d['devices'] if '$vpc_cidr' in x.get('advertisedRoutes',[])))" 2>/dev/null || true)"
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

# --- RESET: restore the pre-feature (baseline) code ----------------------
cmd_reset() {
    install_variant baseline
    warn "Baseline code restored. Re-run 'add-feature' to ship the feature again."
}

# --- ADD-FEATURE: ship the likes feature through the gated pipeline -------
cmd_add_feature() {
    install_variant feature
    export_db_password
    log "Running the FEATURE code through the pipeline (gate -> manual approve -> deploy)"
    "$PY" scripts/run_hybrid_pipeline.py \
        --cdk-path "$CDK_DIR" \
        --ansible-path "$ANSIBLE_DIR" \
        --deploy --manual-approve --verbose
    cmd_approve_route
    log "Uploading the updated frontend (like buttons)"
    cmd_deploy_frontend
    log "Verifying the API"
    sleep 5
    cmd_status
}

# --- Dispatch ------------------------------------------------------------
case "${1:-}" in
    status)          cmd_status ;;
    gate)            cmd_gate ;;
    add-feature)     cmd_add_feature ;;
    reset)           cmd_reset ;;
    deploy-frontend) cmd_deploy_frontend ;;
    approve-route)   cmd_approve_route ;;
    install-variant-feature)  install_variant feature ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -n 36
        exit 1
        ;;
esac
